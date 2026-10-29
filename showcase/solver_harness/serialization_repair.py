"""Consume one durable request-root credit before a capability-free fresh call."""

import uuid

from .budget import budget_reason
from .calls import CallInterrupted


def enabled(config):
    return config.get("features", {}).get("serialization_repair") is True


def repair_failure(harness, run, failed, operation, request):
    """CAS claims survive failures/restart; S3 still admits and bills every dispatch."""
    from .calls import dispatch
    from .storage import SolverEventConflictError, SolverRevisionConflictError

    latest = harness.get_run(run["run_id"])
    state = latest["state"]
    calls = state.get("calls", {})
    root = failed["call_id"]
    for _ in range(len(calls) + 1):
        parent = calls.get(root, {}).get("retry_of")
        if not parent:
            break
        root = parent
    if (not failed.get("serialization_eligible") or request.get("serialization_source")
            or root in state.get("serialization_repairs", {})
            or state["phase"] == "TERMINAL" or budget_reason(state, harness._config)):
        raise CallInterrupted(run["run_id"], failed["call_id"])
    call_id = failed["call_id"] + ":serialization-1"
    try:
        reserved = harness.commit_event(
            run["run_id"], expected_revision=latest["state_revision"],
            event={"event_id": f"serialization-credit-{root}",
                   "type": "serialization_repair_reserved", "call_id": call_id,
                   "claim_id": uuid.uuid4().hex},
            state_updates={
                "serialization_repairs": {**state.get("serialization_repairs", {}), root: call_id},
                "counters": {**state["counters"], "model_calls": state["counters"]["model_calls"] + 1}})
    except (SolverEventConflictError, SolverRevisionConflictError):
        raise CallInterrupted(run["run_id"], failed["call_id"]) from None
    run.clear()
    run.update(reserved)
    repair = {key: request[key] for key in (
        "run_id", "role", "problem_hash", "action", "guidance_request", "solution_candidate",
        "timeout_seconds", "phase_deadline_at", "batch_deadline_at") if key in request}
    repair.update(call_id=call_id, serialization_source=failed["response_ref"],
                  serialization_repair=True, strict_completion=True,
                  allowed_tools=[], tool_policy={"allow": []})
    # solution_candidate binds the controller audit; repair_messages excludes it
    # from the model context, which contains only the original visible reply.
    # No session dispatch: repaired content is validated before the owning role
    # records it. The repair role never sees history or the original question.
    return dispatch(harness, run, operation, repair, lambda _h, _r, invoke, req: invoke(req))
