"""One audited, budgeted ProblemSpec generation before any solving action."""

import hashlib
from collections.abc import Mapping
from copy import deepcopy

from .budget import budget_reason, stop
from .calls import CallInterrupted
from .initial_state import problem_spec_state
from .protocol_repair import (
    completed_call_id,
    interrupted_call,
    known_protocol_failure,
    repair_enabled,
    repair_request,
    reserve_repair,
)
from .specification import normalize_problem_spec

POLICY = {"version": "auto-problem-spec-v1", "status": "pending"}


def intake_pending(run):
    """Only explicitly initialized intake Runs may enter this producer."""
    return (run["state"].get("problem_intake", {}).get("status") == "pending"
            and run["state"]["phase"] != "TERMINAL")


def reject_intake(harness, run, reason):
    """Keep invalid specifications out of solving, without fabricating a fallback."""
    return harness.commit_event(
        run["run_id"], expected_revision=run["state_revision"],
        event={"event_id": "problem-intake-rejected", "type": "problem_intake_rejected",
               "reason": reason},
        state_updates={
            "phase": "TERMINAL", "status": "partial_aborted", "result_reason": reason,
            "problem_intake": {**run["state"]["problem_intake"], "status": "rejected"},
            "final_response": "Problem specification could not be established; no solving was dispatched.",
        },
    )


def _reserve_intake(harness, run, call_id, *, authorized=False):
    """Charge each initial/retry/repair identity once before dispatch."""
    state = run["state"]
    if state["problem_intake"].get("reserved_call_id") == call_id:
        return run
    reason = budget_reason(state, harness._config)
    if reason:
        return stop(harness, run, reason)
    return harness.commit_event(
        run["run_id"], expected_revision=run["state_revision"],
        event={"event_id": f"problem-intake-reserved:{call_id}",
               "type": "problem_intake_retry_reserved" if authorized else "problem_intake_dispatched"},
        state_updates={
            "problem_intake": {**state["problem_intake"], "reserved_call_id": call_id},
            "counters": {**state["counters"], "model_calls": state["counters"]["model_calls"] + 1},
        },
    )


def ensure_problem_spec(harness, run, problem):
    """Consume a completed intake, or dispatch once; unknown calls need explicit retry.

    Public product recovery should call this before population/Explore dispatch,
    after applying its existing authorized_retry decision. This function never
    starts solving and retains the original Run, counters and shared budget.
    """
    if not intake_pending(run):
        return run
    if run["state"].get("clarification", {}).get("status") == "waiting":
        return run
    harness._validate_identity(run, run["run_id"], hashlib.sha256(problem.encode("utf-8")).hexdigest())
    state = run["state"]
    call_id = f"{run['run_id']}:problem-intake:1"
    calls = state.get("calls", {})
    current_id = completed_call_id(calls, call_id)
    record = calls.get(current_id)
    retry = state.get("authorized_retry")
    authorized = (isinstance(retry, Mapping) and retry.get("call_id") == current_id
                  and record is not None and record["status"] in {"unknown_outcome", "dispatched", "streaming"})
    if record is not None and record["status"] == "completed":
        reply = record["response"]
    else:
        known_failure = (record is not None and known_protocol_failure(record)
                         and repair_enabled(harness._config))
        pending_repair = known_failure and not record.get("request", {}).get("repair_instruction")
        if known_failure and not pending_repair:
            raise CallInterrupted(run["run_id"], current_id)
        if record is not None and not authorized and not pending_repair:
            return run
        if harness._model_port is None:
            return reject_intake(harness, run, "problem_intake_port_unavailable")
        request = {
            "run_id": run["run_id"], "call_id": current_id, "role": "problem_intake",
            "session_key": f"problem-intake:{run['run_id']}", "problem": problem,
        }
        if pending_repair:
            request = repair_request(request, failed_call=record)
        reservation = retry["new_call_id"] if authorized else request["call_id"]
        run = _reserve_intake(harness, run, reservation, authorized=authorized)
        if run["state"]["phase"] == "TERMINAL":
            return run
        try:
            reply = harness.dispatch(run, harness._model_port.complete, request)
        except CallInterrupted as exc:
            if pending_repair:
                raise
            run = reserve_repair(harness, run["run_id"], exc,
                failure_event=lambda latest, failed: {
                    "event_id": f"problem-intake-parse:{failed['call_id']}",
                    "type": "problem_intake_parse_failed", "call_id": failed["call_id"],
                })
            failed = interrupted_call(harness, run["run_id"], exc)
            request = repair_request({**request, "call_id": failed["call_id"]}, failed_call=failed)
            run = _reserve_intake(harness, run, request["call_id"])
            if run["state"]["phase"] == "TERMINAL":
                return run
            reply = harness.dispatch(run, harness._model_port.complete, request)
        run = harness.get_run(run["run_id"], problem=problem)
        current_id = completed_call_id(run["state"].get("calls", {}), call_id)
    try:
        spec = normalize_problem_spec(reply)
    except (TypeError, ValueError):
        return reject_intake(harness, run, "problem_intake_invalid_spec")
    if spec["original_problem"] != problem:
        return reject_intake(harness, run, "problem_spec_original_problem_mismatch")
    if spec["specification_version"] != 1:
        return reject_intake(harness, run, "problem_intake_initial_version_invalid")
    updates = {
        **problem_spec_state(spec), "status": "running",
        "problem_intake": {**run["state"]["problem_intake"], "status": "completed",
                           "call_id": current_id, "authority": "generated_task_spec_not_proof"},
    }
    if reply.get("clarification"):
        from .clarification import necessary_question

        try:
            updates.update(necessary_question(run, updates["problem_intake"], reply["clarification"]))
        except (TypeError, ValueError):
            return reject_intake(harness, run, "problem_intake_invalid_clarification")
    if harness._config.get("features", {}).get("concurrent_routes") is True:
        from .population_store import initial_population

        updates["population_policy"] = deepcopy(harness._config["population_policy"])
        updates["population"] = initial_population()
    return harness.commit_event(
        run["run_id"], expected_revision=run["state_revision"],
        event={"event_id": "problem-intake-accepted", "type": "problem_intake_accepted",
               "call_id": current_id, "specification_version": 1}, state_updates=updates,
    )
