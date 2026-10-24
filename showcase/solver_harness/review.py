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
    base_call_id = f"{run_id}:whole-solution-review"
    request = {
        "run_id": run_id,
        "call_id": base_call_id,
        "role": "whole_solution_verifier",
        "session_key": f"whole-review:{run_id}:{reserved['state_revision']}",
        "problem": problem,
        "solution_candidate": candidate,
        "state_revision": reserved["state_revision"],
    }

    def reserve_and_dispatch(current, seq, _continuation_call_id, continuation_request):
        reserved = harness.commit_event(
            current["run_id"],
            expected_revision=current["state_revision"],
            event={
                "event_id": f"review-dispatched-compute-{seq + 1}",
                "type": "solution_review_dispatched",
                "role": "whole_solution_verifier",
            },
            state_updates={
                "counters": {
                    **current["state"]["counters"],
                    "model_calls": current["state"]["counters"]["model_calls"] + 1,
                },
            },
        )
        reply = harness.dispatch(reserved, verifier_port.verify, continuation_request)
        return harness.get_run(current["run_id"]), reply

    from . import protocol_repair
    from .calls import CallInterrupted

    def review_failed(current):
        return harness.commit_event(
            current["run_id"],
            expected_revision=current["state_revision"],
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

    try:
        reply = harness.dispatch(reserved, verifier_port.verify, request)
    except CallInterrupted as exc:
        failed = protocol_repair.interrupted_call(harness, run_id, exc)
        if (
            failed is None
            or not protocol_repair.repair_enabled(harness._config)
            or not protocol_repair.known_protocol_failure(failed)
        ):
            raise
        # One gated format repair with a fresh reviewer identity; a second
        # failure re-raises and still ends dispatch honestly.
        latest = harness.get_run(run_id)
        noted = harness.commit_event(
            run_id,
            expected_revision=latest["state_revision"],
            event={
                "event_id": f"solution-review-parse-{latest['state_revision']}",
                "type": "solution_review_parse_failed",
                "role": "whole_solution_verifier",
                "summary": "Whole-solution review reply failed the response "
                           "protocol; one bounded repair follows",
            },
            state_updates={"status": "running"},
        )
        reserved = harness.commit_event(
            run_id,
            expected_revision=noted["state_revision"],
            event={
                "event_id": "review-dispatched-repair-1",
                "type": "solution_review_dispatched",
                "role": "whole_solution_verifier",
            },
            state_updates={
                "counters": {
                    **noted["state"]["counters"],
                    "model_calls": noted["state"]["counters"]["model_calls"] + 1,
                },
            },
        )
        base_call_id = f"{base_call_id}:repair-1"
        request = protocol_repair.repair_request(request)
        reply = harness.dispatch(reserved, verifier_port.verify, request)
    except Exception:
        return review_failed(reserved)
    from .verifier_compute import continue_review

    run, reply, unfulfilled = continue_review(
        harness,
        reserved,
        role="whole_solution_verifier",
        step_id=None,
        round_number=0,
        attempt_index=run["state"]["attempt_index"],
        base_call_id=base_call_id,
        base_request=request,
        reply=reply,
        reserve_and_dispatch=reserve_and_dispatch,
    )
    if unfulfilled:
        reply = {"verdict": "REJECT", "reason": "verifier_tool_request_unfulfilled"}
    accepted = (
        isinstance(reply, Mapping) and reply.get("verdict") == "ACCEPT" and bool(candidate.strip())
        and not unfulfilled
    )
    next_phase = "TERMINAL" if accepted else "PLAN"
    updates = {"phase": next_phase}
    finding = state["exploration_findings"][-1]
    record = review_record(run, candidate, "ACCEPT" if accepted else "REJECT",
        call_id=base_call_id, origin="explore_polish",
        versions=[{"text": finding.get("original_solution_candidate", candidate)},
                  {"text": candidate}])
    updates["whole_solution_reviews"] = [*state.get("whole_solution_reviews", []), record]
    if accepted:
        updates.update(status="completed_llm_reviewed", final_response=candidate)
    return harness.commit_event(
        run_id,
        expected_revision=run["state_revision"],
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
