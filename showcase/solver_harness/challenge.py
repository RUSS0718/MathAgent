"""Same-step objection replies with bounded verifier sessions."""

from datetime import UTC, datetime

from .step import _normalize_report, run_step
from .traceback import apply_traceback
from .verification import verify_step


def run_challenges(
    harness,
    run,
    *,
    problem,
    model_port,
    verifier_port,
    max_rounds,
    max_model_calls,
    max_runtime_seconds,
):
    """Reply and recheck in verify:{run_id}:plan{version}:step{step_id}."""
    for number in range(1, max_rounds + 1):
        state = run["state"]
        if state["phase"] != "CHALLENGE":
            return run
        attempt = state["attempt_index"]
        suffix = f"-attempt-{attempt}" if attempt else ""
        step_id = state["current_step"]
        record = state["steps"][step_id]
        session = f"verify:{run['run_id']}:plan{state['plan_version']}:step{step_id}{suffix}"
        elapsed = (datetime.now(UTC) - datetime.fromisoformat(state["created_at"])).total_seconds()
        reason = (
            "runtime_budget_exhausted"
            if elapsed >= max_runtime_seconds
            else "model_call_budget_exhausted"
            if state["counters"]["model_calls"] >= max_model_calls
            else None
        )
        if reason:
            return harness.commit_event(
                run["run_id"],
                expected_revision=run["state_revision"],
                event={
                    "event_id": f"challenge-budget-{step_id}-{number}{suffix}",
                    "type": "budget_exhausted",
                    "reason": reason,
                },
                state_updates={
                    "budget": {**state.get("budget", {}), "exhaustion_reason": reason},
                    "status": "partial_budget_exhausted",
                    "final_response": "Budget exhausted during challenge; no verified answer is available.",
                },
            )
        step = next(s for s in state["plan"]["steps"] if s["step_id"] == step_id)
        objection = record["verification"]["objection"]
        if not objection.strip():
            return harness.commit_event(
                run["run_id"],
                expected_revision=run["state_revision"],
                event={
                    "event_id": f"challenge-invalid-{step_id}-{number}{suffix}",
                    "type": "challenge_invalid",
                    "reason": "missing_objection",
                },
                state_updates={
                    "phase": "STEP_VERIFY",
                    "steps": {
                        **state["steps"],
                        step_id: {
                            **record,
                            "verification": {
                                **record["verification"],
                                "valid": False,
                                "reason": "missing_objection",
                            },
                        },
                    },
                },
            )
        counters = {**state["counters"], "model_calls": state["counters"]["model_calls"] + 1}
        run = harness.commit_event(
            run["run_id"],
            expected_revision=run["state_revision"],
            event={
                "event_id": f"challenge-dispatched-{step_id}-{number}{suffix}",
                "type": "challenge_dispatched",
                "round": number,
            },
            state_updates={"counters": counters},
        )
        try:
            reply = model_port.complete(
                {
                    "role": "reasoner",
                    "run_id": run["run_id"],
                    "problem": problem,
                    "call_id": f"{session}:reasoner:{number}",
                    "session_key": session,
                    "step": step,
                    "report": record["report"],
                    "objection": objection,
                    "round": number,
                    "challenge_history": record.get("challenge_history", []),
                    "tool_policy": {"allow": []},
                }
            )
        except Exception:
            reply = {"blocked": True}
        report = _normalize_report(reply, step)
        history = [
            *record.get("challenge_history", []),
            {
                "round": number,
                "session_key": session,
                "objection": objection,
                "reasoner_reply": report,
                "verdict": None,
            },
        ]
        run = harness.commit_event(
            run["run_id"],
            expected_revision=run["state_revision"],
            event={
                "event_id": f"challenge-replied-{step_id}-{number}{suffix}",
                "type": "challenge_replied",
                "round": number,
            },
            state_updates={
                "phase": "STEP_VERIFY",
                "steps": {
                    **state["steps"],
                    step_id: {
                        **record,
                        "report": report,
                        "challenge_history": history,
                    },
                },
            },
        )
        run = verify_step(
            harness,
            run,
            problem=problem,
            verifier_port=verifier_port,
            max_model_calls=max_model_calls,
            max_runtime_seconds=max_runtime_seconds,
            round_number=number,
        )
        updated = run["state"]["steps"][step_id]
        history[-1]["verdict"] = (
            updated["verification"] if run["state"]["phase"] != "TERMINAL" else None
        )
        run = harness.commit_event(
            run["run_id"],
            expected_revision=run["state_revision"],
            event={
                "event_id": f"challenge-recorded-{step_id}-{number}{suffix}",
                "type": "challenge_recorded",
                "round": number,
            },
            state_updates={
                "steps": {
                    **run["state"]["steps"],
                    step_id: {**updated, "challenge_history": history},
                }
            },
        )
    if run["state"]["phase"] != "CHALLENGE":
        return run
    state = run["state"]
    return harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={
            "event_id": f"challenge-stalemate-{step_id}{suffix}",
            "type": "challenge_stalemate",
            "trigger": "STALEMATE",
            "action": "META_DECIDE",
        },
        state_updates={
            "phase": "META_DECIDE",
            "steps": {
                **state["steps"],
                step_id: {**state["steps"][step_id], "status": "STALEMATE"},
            },
            "meta_interventions": [
                *state["meta_interventions"],
                {"trigger": "STALEMATE", "action": "META_DECIDE", "step_id": step_id},
            ],
        },
    )


def run_plan(
    harness,
    run,
    *,
    problem,
    plan,
    model_port,
    verifier_port,
    max_rounds,
    max_model_calls,
    max_runtime_seconds,
):
    """Execute at most the supplied plan, preserving the final review boundary."""
    while True:
        run = run_step(
            harness,
            run,
            problem=problem,
            plan=plan,
            model_port=model_port,
            max_model_calls=max_model_calls,
            max_runtime_seconds=max_runtime_seconds,
        )
        run = verify_step(
            harness,
            run,
            problem=problem,
            verifier_port=verifier_port,
            max_model_calls=max_model_calls,
            max_runtime_seconds=max_runtime_seconds,
        )
        run = run_challenges(
            harness,
            run,
            problem=problem,
            model_port=model_port,
            verifier_port=verifier_port,
            max_rounds=max_rounds,
            max_model_calls=max_model_calls,
            max_runtime_seconds=max_runtime_seconds,
        )
        run = apply_traceback(harness, run)
        if (
            run["state"]["phase"] != "STEP_EXECUTE"
            or run["state"]["counters"]["model_calls"] >= max_model_calls
        ):
            return run
    return run
