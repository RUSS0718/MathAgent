"""Single supplied-plan step execution and conservative report normalization."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
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
    counters = dict(state["counters"])
    elapsed = (datetime.now(UTC) - datetime.fromisoformat(state["created_at"])).total_seconds()
    reason = None
    if elapsed >= max_runtime_seconds:
        reason = "runtime_budget_exhausted"
    elif counters["model_calls"] >= max_model_calls:
        reason = "model_call_budget_exhausted"
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
            "event_id": f"step-dispatched-{step_id}",
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
        reply = model_port.complete(
            harness.prepare_request(
                reserved,
                {
                    "run_id": run["run_id"],
                    "call_id": f"{run['run_id']}:reasoner:{plan['version']}:{step_id}",
                    "role": "reasoner",
                    "problem": problem,
                    "step": dict(step),
                    "state_revision": reserved["state_revision"],
                    "tool_policy": {"allow": []},
                },
            )
        )
    except Exception:
        reply = {"blocked": True}
    report = _normalize_report(reply, step)
    return harness.commit_event(
        run["run_id"],
        expected_revision=reserved["state_revision"],
        event={"event_id": f"step-reported-{step_id}", "type": "step_reported", "step_id": step_id},
        state_updates={
            "phase": "STEP_VERIFY",
            "steps": {**state["steps"], step_id: {"status": "VERIFYING", "report": report}},
        },
    )


def _normalize_report(reply: Any, step: Mapping[str, Any]) -> dict[str, Any]:
    reply = reply if isinstance(reply, Mapping) else {}
    claims = []
    values = reply.get("claims", [])
    for claim in values if isinstance(values, list) else []:
        if isinstance(claim, str):
            claim = {"statement": claim}
        if not isinstance(claim, Mapping) or not isinstance(claim.get("statement"), str):
            continue
        # v1.2 registers no executable tool. Model-supplied refs are never evidence.
        label = claim.get("label")
        claims.append(
            {
                "statement": claim["statement"],
                "label": "easy-verify" if label == "easy-verify" else "hard-verify",
                "tool_evidence_refs": [],
            }
        )
    argument = reply.get("argument", "")
    return {
        "step_id": step["step_id"],
        "objective": step["objective"],
        "argument": argument if isinstance(argument, str) else "",
        "claims": claims,
        "tool_evidence_refs": [],
        "blocked": reply.get("blocked") is True,
    }
