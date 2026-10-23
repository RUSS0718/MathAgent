"""Public recovery decisions evaluated inside the existing Job transaction."""

import json
import time
import uuid

from .run_budget import public_solver_call_id


def recovery_projection(run):
    state = run["state"]
    calls = state.get("calls", {})
    retries = [
        {"call_id": public_solver_call_id(run["run_id"], item["call_id"]),
         "retry_of": public_solver_call_id(run["run_id"], item["retry_of"]),
         "status": item["status"]}
        for item in calls.values() if item.get("retry_of")
    ]
    replaced = {item.get("retry_of") for item in calls.values()}
    unknown = [
        {"call_id": public_solver_call_id(run["run_id"], item["call_id"]),
         "status": "unknown_outcome", "role": item["role"]}
        for item in calls.values()
        if item["status"] in {"dispatched", "streaming", "unknown_outcome"}
        and item["call_id"] not in replaced
    ]
    events = run.get("events", [])
    receipts = {event["event_id"] for event in events if event["type"] == "tool_receipt"}
    unknown_tools = [
        {"call_id": event["event_id"].removesuffix(":dispatch"), "status": "unknown_outcome"}
        for event in events if event["type"] == "tool_dispatched"
        and event["event_id"].removesuffix(":dispatch") not in receipts
    ]
    return {"status": "needs_review" if unknown or unknown_tools else "safe",
            "unknown_calls": unknown, "unknown_tools": unknown_tools, "retries": retries}


def authorize_resume(connection, row, decision):
    """Validate before Job CAS; no network or math writes occur here."""
    from .workspace import WorkspaceError

    identity = json.loads(row["result_json"] or "{}")
    if identity.get("solver_mode") != "star_limited":
        return False
    if row["status"] != "failed" or row["error_code"] not in {
        "needs_review", "star_needs_review", "job_execution_failed"
    }:
        return False
    stored = connection.execute(
        "SELECT state_json FROM solver_states WHERE run_id=?", (row["job_id"],)
    ).fetchone()
    if stored is None:
        raise WorkspaceError("star_recovery_unavailable", status=409)
    state = json.loads(stored[0])
    if state["phase"] == "TERMINAL":
        raise WorkspaceError("star_recovery_terminal", status=409)
    budget = connection.execute(
        "SELECT ledger_json FROM run_budgets WHERE run_id=?", (row["job_id"],)
    ).fetchone()
    if budget is None or time.time() >= json.loads(budget[0])["deadline_at"]:
        raise WorkspaceError("run_deadline_exhausted", status=409)
    receipts = {event[0] for event in connection.execute(
        "SELECT event_id FROM solver_events WHERE run_id=? "
        "AND json_extract(event_json,'$.type')='tool_receipt'", (row["job_id"],)
    )}
    orphan_tools = [action for action in json.loads(budget[0])["actions"]
                    if action["kind"] == "tool" and action.get("tool_call_id") not in receipts]
    if orphan_tools:
        raise WorkspaceError("star_tool_recovery_needs_review", status=409)
    run = {"run_id": row["job_id"], "state": state}
    unknown = recovery_projection(run)["unknown_calls"]
    if unknown:
        if not isinstance(decision, dict) or set(decision) != {"call_id", "new_call_id"}:
            raise WorkspaceError("star_retry_decision_required", status=409)
        old_id, new_id = decision["call_id"], decision["new_call_id"]
        try:
            valid_id = isinstance(new_id, str) and str(uuid.UUID(new_id)) == new_id
        except (ValueError, AttributeError):
            valid_id = False
        old = next((item for item in state.get("calls", {}).values()
                    if public_solver_call_id(row["job_id"], item["call_id"]) == old_id
                    and any(item_id["call_id"] == old_id for item_id in unknown)), None)
        if old is None or not valid_id or new_id in state["calls"]:
            raise WorkspaceError("star_retry_identity_invalid", status=409)
        identity["retry_call"] = {"call_id": old["call_id"], "new_call_id": new_id}
    elif decision is not None:
        raise WorkspaceError("star_retry_not_unknown", status=409)
    connection.execute("UPDATE workspace_jobs SET result_json=? WHERE job_id=?",
                       (json.dumps(identity), row["job_id"]))
    return True


def resume_solver(harness, problem, run_id, retry):
    """Re-enter the owning STAR phase using audited responses when available."""
    from .solver_harness.controller import run_supplied_plan_or_explore

    run = harness.get_run(run_id, problem=problem)
    if retry is not None:
        run = harness.commit_event(
            run_id, expected_revision=run["state_revision"],
            event={"event_id": "retry-authorized-" + retry["new_call_id"],
                   "type": "call_retry_authorized", "retry_of": retry["call_id"]},
            state_updates={"authorized_retry": retry, "status": "running"},
        )
    if recovery_projection(run)["unknown_calls"] and retry is None:
        return run
    if run["state"]["phase"] in {"STEP_EXECUTE", "STEP_VERIFY", "CHALLENGE"}:
        return run_supplied_plan_or_explore(
            harness, run, problem, {"plan": run["state"]["plan"]}
        )
    if run["state"]["phase"] in {"SETUP", "EXPLORE", "EXPLORE_REVIEW"}:
        from .solver_harness.calls import pending_call
        from .solver_harness.review import review_solution

        pending = pending_call(run)
        progress = [event for event in run["events"]
                    if event["type"] not in {"call_audit", "session_started", "session_recorded",
                                              "call_retry_authorized"}
                    and not event["type"].endswith("_dispatched")]
        polished = progress and progress[-1]["type"] == "exploration_polished"
        if polished or (pending is not None and pending["role"] == "whole_solution_verifier"):
            return review_solution(
                harness, run, problem=problem, verifier_port=harness._verifier_port,
                max_model_calls=harness._config["max_model_calls"],
                max_runtime_seconds=harness._config["max_total_duration_seconds"],
            )
        return run_supplied_plan_or_explore(harness, run, problem, {})
    return harness.solve(problem, {"run_id": run_id})
