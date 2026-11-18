"""Population delivery must retain a complete physical ledger and known proof sources."""

import json


def delivery_allowed(connection, state):
    """Check independent proof sources without requiring unrelated requests to settle."""
    row = connection.execute(
        "SELECT ledger_json FROM run_budgets WHERE run_id=?", (state["run_id"],)
    ).fetchone()
    if row is None:
        return False, "population_ledger_incomplete"
    try:
        ledger = json.loads(row[0])
        resources = ledger["actions"]
        if not isinstance(resources, list) or not isinstance(ledger["limits"], dict):
            return False, "population_ledger_incomplete"
    except (ValueError, KeyError, TypeError):
        return False, "population_ledger_incomplete"
    population = state.get("population", {})
    actions = population.get("actions", {})
    calls = state.get("calls", {})
    if connection.execute("SELECT 1 FROM sqlite_master WHERE name='workspace_events'").fetchone():
        physical_ids = {item.get("id") for item in resources if item.get("kind") == "http"}
        for row in connection.execute(
            "SELECT payload_json FROM workspace_events WHERE job_id=? AND event_type='request_attempt'",
            (state["run_id"],),
        ):
            attempt = json.loads(row[0]).get("attempt")
            attempt_id = attempt.get("attempt_id") if isinstance(attempt, dict) else None
            if not isinstance(attempt_id, str) or not attempt_id or attempt_id not in physical_ids:
                return False, "population_ledger_incomplete"
    ledger_calls = {
        item.get("solver_call_id") for item in resources if item.get("kind") == "logical"
    }
    for call in calls.values():
        if call.get("status") in {"completed", "dispatched", "streaming", "unknown_outcome"}:
            if call.get("call_id") not in ledger_calls:
                return False, "population_ledger_incomplete"
            logical_ids = {item.get("logical_call_id") for item in resources
                           if item.get("kind") == "logical"
                           and item.get("solver_call_id") == call.get("call_id")}
            physical = [item for item in resources if item.get("kind") == "http"
                        and (item.get("solver_call_id") == call.get("call_id")
                             or item.get("logical_call_id") in logical_ids)
                        and item.get("status") != "pre_reserved"]
            if not physical:
                return False, "population_ledger_incomplete"
            if call.get("status") in {"dispatched", "streaming", "unknown_outcome"}:
                if any(item.get("status") in {"reserved", "unknown", "error"}
                       and (not isinstance(item.get("input_estimate"), int)
                            or not isinstance(item.get("output_cap"), int)) for item in physical):
                    return False, "population_ledger_incomplete"
    for action in actions.values():
        if action.get("status") in {"inflight", "unknown"}:
            held = [
                item
                for item in resources
                if item.get("population_action_id") == action["action_id"]
            ]
            if not any(item.get("kind") == "http" for item in held):
                return False, "population_ledger_incomplete"
    sources = set()
    for item in [
        *state.get("verified_results_ledger", []),
        *state.get("obligation_evidence_ledger", []),
    ]:
        if item.get("invalidated") is True or item.get("valid") is False:
            continue
        call_id = item.get("review_call_id")
        if call_id:
            sources.add(call_id)
    for call_id in sources:
        call = calls.get(call_id, {})
        action = actions.get(call.get("action_id"), {})
        if (
            call.get("status") != "completed"
            or action.get("status") != "completed"
            or action.get("accepted") is not True
        ):
            return False, "population_unknown_proof_dependency"
        from .population_evidence import validate_dependencies

        if not validate_dependencies(state, action.get("dependencies", []))[0]:
            return False, "population_proof_dependency_changed"
    return True, None
