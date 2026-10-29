"""Independent noncoding falsification of a Verifier-declared incomplete claim."""

from collections.abc import Mapping
from copy import deepcopy

from .budget import budget_reason, stop
from .calls import CallInterrupted
from .protocol_repair import completed_call_id


def pending_review(run):
    """Resume a declared falsification action without dispatching its Verifier again."""
    from .calls import pending_call

    call = pending_call(run)
    if call is None or call.get("request", {}).get("action") != "counterexample_check":
        return None
    step = run["state"].get("steps", {}).get(run["state"].get("current_step"), {})
    for record in step.get("counterexample_checks", {}).values():
        if completed_call_id(run["state"].get("calls", {}), record["call_id"]) == call.get("call_id"):
            calls = run["state"].get("calls", {})
            verifier = calls.get(completed_call_id(calls, record["verifier_call_id"]), {})
            if verifier.get("status") == "completed":
                return record["verifier_call_id"], deepcopy(verifier["response"])
    return None


def target(report, declaration):
    """Bind a structured declaration to an actual claim; do not infer mathematics."""
    if not isinstance(declaration, Mapping):
        return None
    index = declaration.get("claim_index")
    claims = report.get("claims", [])
    if (
        set(declaration) - {"claim_type"} != {
            "claim_index", "both_directions_proved", "assumptions", "approach"}
        or ("claim_type" in declaration and (
            not isinstance(declaration["claim_type"], str) or declaration["claim_type"] not in {
                "numerical_evaluation", "sharp_bound", "extremum",
                "necessary_and_sufficient", "general_proof"}))
        or type(index) is not int or not 0 <= index < len(claims)
        or type(declaration.get("both_directions_proved")) is not bool
        or not isinstance(declaration.get("assumptions"), list)
        or not all(isinstance(item, str) and item.strip() for item in declaration["assumptions"])
        or not isinstance(declaration.get("approach"), str) or not declaration["approach"].strip()
        or not isinstance(claims[index].get("statement"), str) or not claims[index]["statement"].strip()
    ):
        return None
    return {**deepcopy(dict(declaration)), "claim": claims[index]["statement"]}


def missing_direction(declared):
    """Legacy declarations remain applicable; finite evaluation has no converse."""
    return (declared.get("claim_type") != "numerical_evaluation"
            and not declared["both_directions_proved"])


def run_check(harness, run, *, problem, declared, verifier_call_id):
    reason = budget_reason(run["state"], harness._config)
    if reason:
        return stop(harness, run, reason)
    if harness._model_port is None:
        return run
    state = run["state"]
    step_id = state["current_step"]
    call_id = f"{verifier_call_id}:counterexample"
    record = {
        "verifier_call_id": verifier_call_id, "call_id": call_id,
        "target": deepcopy(declared), "status": "requested", "result": None,
    }
    if pending_review(run) is None:
        checks = {**state["steps"][step_id].get("counterexample_checks", {}), verifier_call_id: record}
        run = harness.commit_event(
            run["run_id"], expected_revision=run["state_revision"],
            event={"event_id": f"counterexample-requested-{run['state_revision']}",
                   "type": "counterexample_requested", "step_id": step_id, "role": "researcher"},
            state_updates={
                "counters": {**state["counters"], "model_calls": state["counters"]["model_calls"] + 1},
                "steps": {**state["steps"], step_id: {**state["steps"][step_id],
                                                    "counterexample_checks": checks}},
            },
        )
    request = {
        "run_id": run["run_id"], "call_id": call_id, "role": "researcher",
        "action": "counterexample_check", "session_key": call_id,
        "problem": problem, "claim": declared["claim"],
        "assumptions": declared["assumptions"], "forbidden_direction": declared["approach"],
        "prior_conjectures": [
            item["statement"] for item in state.get("verified_results_ledger", [])
            if isinstance(item, Mapping) and item.get("category") == "Conjecture"
            and isinstance(item.get("statement"), str)
        ] + [
            check["target"]["claim"] for step in state.get("steps", {}).values()
            for check in step.get("counterexample_checks", {}).values()
            if check.get("evidence_category") == "Conjecture"
        ],
        "suspected_false_claim": True, "allowed_tools": [], "tool_policy": {"allow": []},
        "instruction": "Independently try to refute this exact claim within all assumptions. "
                       "Use no code, tools or cross-run context. NOT_FOUND is bounded search, not proof.",
    }
    result = None
    try:
        result = harness.dispatch(run, harness._model_port.complete, request)
    except CallInterrupted:
        latest = harness.get_run(run["run_id"])
        call = latest["state"].get("calls", {}).get(call_id, {})
        if call.get("error_category") not in {
            "invalid_role_schema", "invalid_json", "empty_response", "truncated_response",
        }:
            raise
        run = latest
    except Exception:
        run = harness.get_run(run["run_id"])
    valid = valid_result(result)
    record["call_id"] = completed_call_id(run["state"].get("calls", {}), call_id)
    record.update(status="completed" if valid else "invalid", result=deepcopy(result) if valid else None)
    if valid:
        record["evidence_category"] = (
            "Counterexample" if result["verdict"] == "FOUND_COUNTEREXAMPLE" else "Conjecture"
        )
    state = run["state"]
    checks = {**state["steps"][step_id].get("counterexample_checks", {}), verifier_call_id: record}
    return harness.commit_event(
        run["run_id"], expected_revision=run["state_revision"],
        event={"event_id": f"counterexample-completed-{run['state_revision']}",
               "type": "counterexample_completed", "step_id": step_id, "role": "researcher",
               "counterexample_verdict": result["verdict"] if valid else "INVALID"},
        state_updates={"steps": {**state["steps"], step_id: {**state["steps"][step_id],
                                                           "counterexample_checks": checks}}},
    )


def valid_result(result):
    if not isinstance(result, Mapping) or set(result) != {
        "verdict", "counterexample", "assumptions_checked", "violated_conclusion", "searched_scope",
    }:
        return False
    if (
        result["verdict"] not in {"FOUND_COUNTEREXAMPLE", "NOT_FOUND"}
        or not all(isinstance(result[key], str) for key in
                   ("counterexample", "violated_conclusion", "searched_scope"))
        or not result["searched_scope"].strip()
        or not isinstance(result["assumptions_checked"], list)
        or not all(isinstance(item, str) and item.strip() for item in result["assumptions_checked"])
    ):
        return False
    return result["verdict"] == "NOT_FOUND" or bool(
        result["counterexample"].strip() and result["violated_conclusion"].strip()
        and result["assumptions_checked"]
    )


def consumed_result(state, *, step_id, verifier_call_id, declared):
    """A model-supplied PASS or a skipped dispatcher is not a completed action."""
    record = state["steps"][step_id].get("counterexample_checks", {}).get(verifier_call_id, {})
    call = state.get("calls", {}).get(record.get("call_id"), {})
    result = record.get("result")
    if (
        record.get("status") != "completed" or record.get("target") != declared
        or record.get("verifier_call_id") != verifier_call_id
        or call.get("status") != "completed" or call.get("role") != "researcher"
        or call.get("request", {}).get("action") != "counterexample_check"
        or call.get("request", {}).get("claim") != declared["claim"]
        or call.get("response") != result or not valid_result(result)
    ):
        return None
    return result
