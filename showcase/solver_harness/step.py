"""Single supplied-plan step execution and conservative report normalization."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .explore import ModelPort, _HarnessOperations


def run_step(
    harness: _HarnessOperations,
    run: dict[str, Any],
    *,
    problem: str,
    plan: Mapping[str, Any],
    model_port: ModelPort,
    max_model_calls: int,
    max_runtime_seconds: int,
) -> dict[str, Any]:
    """Execute the first supplied step once, leaving the report pending review."""
    state = run["state"]
    step = next(
        (item for item in plan["steps"] if item["step_id"] == state["current_step"]),
        plan["steps"][0],
    )
    step_id = step["step_id"]
    attempt = state["attempt_index"]
    previous = state["steps"].get(step_id, {})
    challenge_history = previous.get("challenge_history", [])
    suffix = f"-attempt-{attempt}" if attempt else ""
    if challenge_history:
        suffix += f"-challenge-continuation-{len(challenge_history)}"
    session = f"reasoner:{run['run_id']}:plan{plan['version']}:attempt{attempt}"
    counters = dict(state["counters"])
    from .budget import budget_reason

    reason = budget_reason(state, {"max_model_calls": max_model_calls,
                                   "max_total_duration_seconds": max_runtime_seconds})
    if reason is not None:
        return harness.commit_event(
            run["run_id"],
            expected_revision=run["state_revision"],
            event={
                "event_id": "step-budget-exhausted",
                "type": "budget_exhausted",
                "reason": reason,
            },
            state_updates={
                "phase": "TERMINAL",
                "status": "partial_budget_exhausted",
                "budget": {**state.get("budget", {}), "exhaustion_reason": reason},
                "final_response": "Budget exhausted before step execution; no verified answer is available.",
            },
        )
    counters["model_calls"] += 1
    reserved = harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={
            "event_id": f"step-dispatched-{step_id}{suffix}",
            "type": "step_dispatched",
            "step_id": step_id,
        },
        state_updates={
            "phase": "STEP_EXECUTE",
            "plan": dict(plan),
            "plan_version": plan["version"],
            "current_step": step_id,
            "counters": counters,
        },
    )
    try:
        request = {
            "run_id": run["run_id"],
            "call_id": f"{run['run_id']}:reasoner:{plan['version']}:{step_id}{suffix}",
            "session_key": session,
            "failure_records": state["failure_records"],
            "rescued_results": state.get("rescued_results", []),
            "role": "reasoner",
            "problem": problem,
            "step": dict(step),
            "state_revision": reserved["state_revision"],
            "tool_policy": {"allow": []},
        }
        guidance_task = state.get("pending_guidance_task")
        guidance = state.get("meta_guidance_decision")
        if isinstance(guidance_task, str) and guidance_task.strip():
            request["specific_task"] = guidance_task
        if challenge_history:
            request["challenge_history"] = challenge_history
            request["objection"] = previous.get("verification", {}).get("objection", "")
        reply = harness.dispatch(
            reserved,
            model_port.complete,
            request,
        )
    except Exception:
        reply = {"blocked": True}
    report = _normalize_report(reply, step)
    updates = {
        "phase": "STEP_VERIFY",
        "steps": {
            **state["steps"],
            step_id: {**previous, "status": "VERIFYING", "report": report},
        },
    }
    action_type = guidance.get("action_type") if isinstance(guidance, Mapping) else None
    failure_type = next(
        (
            item.get("failure_type")
            for item in reversed(state.get("meta_interventions", []))
            if item.get("kind") == "guidance"
            and item.get("plan_version") == state["plan_version"]
            and item.get("step_id") == step_id
        ),
        None,
    )
    if request.get("specific_task"):
        updates["pending_guidance_task"] = None
    run = harness.commit_event(
        run["run_id"],
        expected_revision=reserved["state_revision"],
        event={
            "event_id": f"step-reported-{step_id}{suffix}",
            "type": "step_reported",
            "step_id": step_id,
        },
        state_updates=updates,
    )
    if request.get("specific_task"):
        run = harness.commit_event(
            run["run_id"],
            expected_revision=run["state_revision"],
            event={
                "event_id": f"meta-guidance-applied-{run['state_revision']}",
                "type": "meta_guidance_applied",
                "step_id": step_id,
                "failure_type": failure_type,
                "action_type": action_type,
                "specific_task_consumed": True,
                **({"decision_revision": guidance["decided_at_revision"]}
                   if isinstance(guidance, Mapping)
                   and isinstance(guidance.get("decided_at_revision"), int) else {}),
            },
        )
    return run


def _normalize_report(reply: Any, step: Mapping[str, Any]) -> dict[str, Any]:
    reply = reply if isinstance(reply, Mapping) else {}
    claims = []
    values = reply.get("claims", [])
    for claim in values if isinstance(values, list) else []:
        if isinstance(claim, str):
            claim = {"statement": claim}
        if not isinstance(claim, Mapping) or not isinstance(claim.get("statement"), str):
            continue
        # Model-supplied refs never establish evidence; prechecks own receipts.
        label = claim.get("label")
        claims.append(
            {
                "statement": claim["statement"],
                "label": "easy-verify" if label == "easy-verify" else "hard-verify",
                "tool_evidence_refs": [],
            }
        )
        if label == "easy-verify" and isinstance(claim.get("tool_request"), Mapping):
            claims[-1]["tool_request"] = dict(claim["tool_request"])
    argument = reply.get("argument", "")
    candidate = reply.get("solution_candidate")
    extra = {}
    if isinstance(candidate, str):
        extra = {
            "solution_candidate": candidate,
            "answer_completeness": reply.get("answer_completeness", "partial"),
        }
    return {
        **extra,
        "step_id": step["step_id"],
        "objective": step["objective"],
        "argument": argument if isinstance(argument, str) else "",
        "claims": claims,
        "tool_evidence_refs": [],
        "blocked": reply.get("blocked") is True,
    }
