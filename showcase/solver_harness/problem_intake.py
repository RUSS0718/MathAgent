"""One audited, budgeted ProblemSpec generation before any solving action."""

import hashlib
from collections.abc import Mapping
from copy import deepcopy

from .budget import budget_reason, stop
from .calls import latest_retry_id
from .initial_state import problem_spec_state
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


def ensure_problem_spec(harness, run, problem):
    """Consume a completed intake, or dispatch once; unknown calls need explicit retry.

    Public product recovery should call this before population/Explore dispatch,
    after applying its existing authorized_retry decision. This function never
    starts solving and retains the original Run, counters and shared budget.
    """
    if not intake_pending(run):
        return run
    harness._validate_identity(run, run["run_id"], hashlib.sha256(problem.encode("utf-8")).hexdigest())
    state = run["state"]
    call_id = f"{run['run_id']}:problem-intake:1"
    calls = state.get("calls", {})
    current_id = latest_retry_id(calls, call_id)
    record = calls.get(current_id)
    retry = state.get("authorized_retry")
    authorized = (isinstance(retry, Mapping) and retry.get("call_id") == current_id
                  and record is not None and record["status"] in {"unknown_outcome", "dispatched", "streaming"})
    if record is not None and record["status"] == "completed":
        reply = record["response"]
    else:
        if record is not None and not authorized:
            return run
        if harness._model_port is None:
            return reject_intake(harness, run, "problem_intake_port_unavailable")
        reservation = retry["new_call_id"] if authorized else call_id
        if state["problem_intake"].get("reserved_call_id") != reservation:
            reason = budget_reason(state, harness._config)
            if reason:
                return stop(harness, run, reason)
            run = harness.commit_event(
                run["run_id"], expected_revision=run["state_revision"],
                event={"event_id": f"problem-intake-reserved:{reservation}",
                       "type": "problem_intake_dispatched" if not authorized else "problem_intake_retry_reserved"},
                state_updates={
                    "problem_intake": {**state["problem_intake"], "reserved_call_id": reservation},
                    "counters": {**state["counters"], "model_calls": state["counters"]["model_calls"] + 1},
                },
            )
        reply = harness.dispatch(run, harness._model_port.complete, {
            "run_id": run["run_id"], "call_id": call_id, "role": "problem_intake",
            "session_key": f"problem-intake:{run['run_id']}", "problem": problem,
        })
        run = harness.get_run(run["run_id"], problem=problem)
        current_id = latest_retry_id(run["state"].get("calls", {}), call_id)
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
    if harness._config.get("features", {}).get("concurrent_routes") is True:
        from .population_store import initial_population

        updates["population_policy"] = deepcopy(harness._config["population_policy"])
        updates["population"] = initial_population()
    return harness.commit_event(
        run["run_id"], expected_revision=run["state_revision"],
        event={"event_id": "problem-intake-accepted", "type": "problem_intake_accepted",
               "call_id": current_id, "specification_version": 1}, state_updates=updates,
    )
