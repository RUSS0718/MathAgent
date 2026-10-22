"""Strict step review and evidence persistence for supplied plans."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

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
    state = run["state"]
    suffix = f"-challenge-{round_number}" if round_number else ""
    attempt = state["attempt_index"]
    suffix += f"-attempt-{attempt}" if attempt else ""
    step_id = state["current_step"]
    plan = state["plan"]
    index = next(i for i, step in enumerate(plan["steps"]) if step["step_id"] == step_id)
    step = plan["steps"][index]
    counters = dict(state["counters"])
    elapsed = (datetime.now(UTC) - datetime.fromisoformat(state["created_at"])).total_seconds()
    reason = None
    if elapsed >= max_runtime_seconds:
        reason = "runtime_budget_exhausted"
    elif counters["model_calls"] >= max_model_calls:
        reason = "model_call_budget_exhausted"
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
    try:
        reply = harness.dispatch(
            reserved,
            verifier_port.verify,
            {
                "run_id": run["run_id"],
                "call_id": f"{run['run_id']}:step-verifier:{plan['version']}:{step_id}{suffix}",
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
    return harness.commit_event(
        run["run_id"],
        expected_revision=reserved["state_revision"],
        event={
            "event_id": f"step-reviewed-{step_id}{suffix}",
            "type": "step_reviewed",
            "step_id": step_id,
            **verification,
        },
        state_updates={
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
        },
    )
