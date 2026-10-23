"""Explicit offline whole-solution review for Explore candidates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from .explore import _HarnessOperations
from .final_binding import review_record


class VerifierPort(Protocol):
    """Whole-solution review boundary; replies contain an ACCEPT/REJECT verdict."""

    def verify(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


class ScriptedVerifierPort:
    """Offline verifier returning scripted replies without any network calls."""

    def __init__(self, responses: Sequence[Mapping[str, Any]]) -> None:
        self._responses = [dict(response) for response in responses]
        self.requests: list[dict[str, Any]] = []

    def verify(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        self.requests.append(dict(request))
        return self._responses.pop(0) if self._responses else {"verdict": "REJECT"}


def review_solution(
    harness: _HarnessOperations,
    run: dict[str, Any],
    *,
    problem: str,
    verifier_port: VerifierPort | None,
    max_model_calls: int,
    max_runtime_seconds: int,
) -> dict[str, Any]:
    """Reserve a review call and persist only the verdict and final candidate."""
    state = run["state"]
    run_id = run["run_id"]
    if verifier_port is None:
        return harness.commit_event(
            run_id,
            expected_revision=run["state_revision"],
            event={
                "event_id": "review-unavailable",
                "type": "solution_review_unavailable",
                "summary": "No whole-solution verifier configured; candidate remains unverified",
            },
            state_updates={
                "phase": "TERMINAL",
                "status": "completed_unverified",
                "final_response": "Whole-solution review unavailable; no verified answer is available.",
            },
        )
    counters = dict(state["counters"])
    from .budget import budget_reason

    reason = budget_reason(state, {"max_model_calls": max_model_calls,
                                   "max_total_duration_seconds": max_runtime_seconds})
    if reason is not None:
        return harness.commit_event(
            run_id,
            expected_revision=run["state_revision"],
            event={
                "event_id": "review-budget-exhausted",
                "type": "budget_exhausted",
                "reason": reason,
            },
            state_updates={
                "phase": "TERMINAL",
                "status": "partial_budget_exhausted",
                "budget": {**state.get("budget", {}), "exhaustion_reason": reason},
                "final_response": "Budget exhausted before completing solution review; no verified answer is available.",
            },
        )
    candidate = state["exploration_findings"][-1].get("solution_candidate", "")
    counters["model_calls"] += 1
    reserved = harness.commit_event(
        run_id,
        expected_revision=run["state_revision"],
        event={"event_id": "review-dispatched", "type": "solution_review_dispatched"},
        state_updates={"counters": counters},
    )
    try:
        reply = harness.dispatch(
            reserved,
            verifier_port.verify,
            {
                "run_id": run_id,
                "call_id": f"{run_id}:whole-solution-review",
                "role": "whole_solution_verifier",
                "session_key": f"whole-review:{run_id}:{reserved['state_revision']}",
                "problem": problem,
                "solution_candidate": candidate,
                "state_revision": reserved["state_revision"],
            },
        )
    except Exception:
        return harness.commit_event(
            run_id,
            expected_revision=reserved["state_revision"],
            event={
                "event_id": "review-failed",
                "type": "solution_review_failed",
                "summary": "Whole-solution verifier failed; candidate remains unverified",
            },
            state_updates={
                "phase": "TERMINAL",
                "status": "failed_runtime",
                "final_response": "Solution review failed; no verified answer is available.",
            },
        )
    accepted = (
        isinstance(reply, Mapping) and reply.get("verdict") == "ACCEPT" and bool(candidate.strip())
    )
    next_phase = "TERMINAL" if accepted else "PLAN"
    updates = {"phase": next_phase}
    finding = state["exploration_findings"][-1]
    record = review_record(reserved, candidate, "ACCEPT" if accepted else "REJECT",
        call_id=f"{run_id}:whole-solution-review", origin="explore_polish",
        versions=[{"text": finding.get("original_solution_candidate", candidate)},
                  {"text": candidate}])
    updates["whole_solution_reviews"] = [*state.get("whole_solution_reviews", []), record]
    if accepted:
        updates.update(status="completed_llm_reviewed", final_response=candidate)
    return harness.commit_event(
        run_id,
        expected_revision=reserved["state_revision"],
        event={
            "event_id": "review-assessed",
            "type": "solution_review_assessed",
            "verdict": "ACCEPT" if accepted else "REJECT",
            "next_phase": next_phase,
            **{
                key: reply[key]
                for key in ("reason", "counterexample")
                if isinstance(reply, Mapping) and isinstance(reply.get(key), str)
            },
        },
        state_updates=updates,
    )
