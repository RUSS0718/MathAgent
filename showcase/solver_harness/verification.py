"""Strict step review and evidence persistence for supplied plans."""

from collections.abc import Mapping
from typing import Any

from .calls import CallInterrupted
from .explore import _HarnessOperations
from .review import VerifierPort


def normalize_verdict(reply: Any, current_index: int) -> dict[str, Any]:
    """Interpret exact structured enum values; never infer acceptance from prose."""
    reply = reply if isinstance(reply, Mapping) else {}
    goal = reply.get("goal_gate")
    logic = reply.get("logic_gate")
    verdict = reply.get("verdict")
    target = reply.get("trace_back_to")
    valid = (
        isinstance(goal, str)
        and goal in ("YES", "PARTIAL", "NO")
        and isinstance(logic, str)
        and logic in ("PASS", "FAIL", "UNCERTAIN")
        and isinstance(verdict, str)
        and verdict in ("ACCEPT", "CHALLENGE", "TRACE_BACK", "PROPOSE_REPLAN")
    )
    if verdict == "ACCEPT" and (goal != "YES" or logic != "PASS"):
        valid = False
    if verdict == "TRACE_BACK" and (
        isinstance(target, bool) or not isinstance(target, int) or not 1 <= target <= current_index
    ):
        valid = False
    return {
        "goal_gate": goal if isinstance(goal, str) else None,
        "logic_gate": logic if isinstance(logic, str) else None,
        "verdict": verdict if isinstance(verdict, str) else None,
        "trace_back_to": target
        if isinstance(target, int) and not isinstance(target, bool)
        else None,
        "valid": bool(valid),
    }


def verify_step(
    harness: _HarnessOperations,
    run: dict[str, Any],
    *,
    problem: str,
    verifier_port: VerifierPort | None,
    max_model_calls: int,
    max_runtime_seconds: int,
    round_number: int = 0,
) -> dict[str, Any]:
    """Review one report once, leaving later phases to their owning slices."""
    if verifier_port is None or run["state"]["phase"] != "STEP_VERIFY":
        return run
    run = harness.precheck_report(run)
    from .budget import budget_reason, stop

    reason = budget_reason(run["state"], harness._config)
    if reason:
        return stop(harness, run, reason)
    state = run["state"]
    suffix = f"-challenge-{round_number}" if round_number else ""
    attempt = state["attempt_index"]
    suffix += f"-attempt-{attempt}" if attempt else ""
    step_id = state["current_step"]
    plan = state["plan"]
    index = next(i for i, step in enumerate(plan["steps"]) if step["step_id"] == step_id)
    step = plan["steps"][index]
    counters = dict(state["counters"])
    from .budget import budget_reason

    reason = budget_reason(state, {"max_model_calls": max_model_calls,
                                   "max_total_duration_seconds": max_runtime_seconds})
    if reason:
        return harness.commit_event(
            run["run_id"],
            expected_revision=run["state_revision"],
            event={
                "event_id": f"step-review-budget-{step_id}{suffix}",
                "type": "budget_exhausted",
                "reason": reason,
            },
            state_updates={
                "phase": "TERMINAL",
                "status": "partial_budget_exhausted",
                "budget": {**state.get("budget", {}), "exhaustion_reason": reason},
                "final_response": "Budget exhausted before step review; no verified answer is available.",
            },
        )
    counters["model_calls"] += 1
    reserved = harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={
            "event_id": f"step-review-dispatched-{step_id}{suffix}",
            "type": "step_review_dispatched",
            "step_id": step_id,
        },
        state_updates={"counters": counters},
    )
    report = state["steps"][step_id]["report"]
    call_id = f"{run['run_id']}:step-verifier:{plan['version']}:{step_id}{suffix}"
    try:
        reply = harness.dispatch(
            reserved,
            verifier_port.verify,
            {
                "run_id": run["run_id"],
                "call_id": call_id,
                "session_key": f"verify:{run['run_id']}:plan{plan['version']}:step{step_id}"
                + (f"-attempt-{attempt}" if attempt else ""),
                "round": round_number,
                "challenge_history": state["steps"][step_id].get("challenge_history", []),
                "role": "step_verifier",
                "problem": problem,
                "step": step,
                "report": report,
                "current_step_index": index + 1,
                "state_revision": reserved["state_revision"],
            },
        )
    except CallInterrupted:
        latest = harness.get_run(run["run_id"])
        call = latest["state"].get("calls", {}).get(call_id, {})
        if call.get("error_category") not in {
            "invalid_role_schema", "invalid_json", "empty_response", "truncated_response"
        }:
            return latest
        failed_review = normalize_verdict(None, index + 1)
        failed_review.update(objection="", reason="invalid_verifier_response")
        return harness.commit_event(
            run["run_id"],
            expected_revision=latest["state_revision"],
            event={
                "event_id": f"step-review-invalid-{step_id}{suffix}",
                "type": "step_reviewed",
                "step_id": step_id,
                **failed_review,
                "summary": "Verifier response was invalid; the step was not accepted",
            },
            state_updates={
                "phase": "STEP_VERIFY",
                "status": "partial_aborted",
                "current_step": step_id,
                "steps": {
                    **latest["state"]["steps"],
                    step_id: {
                        **latest["state"]["steps"][step_id],
                        "status": "VERIFYING",
                        "verification": failed_review,
                    },
                },
            },
        )
    except Exception:
        reply = None
    verification = normalize_verdict(reply, index + 1)
    verification["objection"] = (
        reply.get("objection", "")
        if isinstance(reply, Mapping) and isinstance(reply.get("objection", ""), str)
        else ""
    )
    if isinstance(reply, Mapping):
        if isinstance(reply.get("reason"), str):
            verification["reason"] = reply["reason"]
        directions = reply.get("forbidden_directions")
        if isinstance(directions, list) and all(isinstance(item, str) for item in directions):
            verification["forbidden_directions"] = directions
    accepted = verification["valid"] and verification["verdict"] == "ACCEPT"
    phase = "STEP_VERIFY"
    current_step = step_id
    evidence = []
    if accepted:
        phase = "STEP_EXECUTE" if index + 1 < len(plan["steps"]) else "FINAL_GENERATE"
        current_step = (
            plan["steps"][index + 1]["step_id"] if index + 1 < len(plan["steps"]) else None
        )
        statements = [claim["statement"] for claim in report["claims"]]
        if not statements and report["argument"].strip():
            statements = [report["argument"]]
        evidence = [
            {
                "category": "step_result",
                "statement": statement,
                "source": step_id,
                "evidence_level": "llm_reviewed",
                "dependencies": step.get("depends_on", []),
            }
            for statement in statements
        ]
    elif verification["valid"]:
        phase = {
            "CHALLENGE": "CHALLENGE",
            "TRACE_BACK": "TRACE_BACK",
            "PROPOSE_REPLAN": "META_DECIDE",
        }[verification["verdict"]]
    state_updates = {
        "phase": phase,
        "current_step": current_step,
        "steps": {
            **state["steps"],
            step_id: {
                **state["steps"][step_id],
                "status": "ACCEPTED" if accepted else "VERIFYING",
                "verification": verification,
            },
        },
        "accepted_results": [*state["accepted_results"], *evidence],
    }
    if not verification["valid"]:
        state_updates["status"] = "partial_aborted"
    return harness.commit_event(
        run["run_id"],
        expected_revision=reserved["state_revision"],
        event={
            "event_id": f"step-reviewed-{step_id}{suffix}",
            "type": "step_reviewed",
            "step_id": step_id,
            **verification,
        },
        state_updates=state_updates,
    )
