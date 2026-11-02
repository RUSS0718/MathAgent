"""Deterministic Explore routing for the Solver Harness."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

_ASSESSMENTS = frozenset({"SOLVED", "PARTIALLY_SOLVED", "NEED_PLAN", "UNKNOWN"})


class ModelPort(Protocol):
    """Minimal synchronous model boundary used by the explicit Harness entry."""

    def complete(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


class ScriptedModelPort:
    """Offline ModelPort that returns provided assessments in order."""

    def __init__(self, responses: Sequence[Mapping[str, Any]]) -> None:
        self._responses = [dict(response) for response in responses]
        self.requests: list[dict[str, Any]] = []

    def complete(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        self.requests.append(dict(request))
        if not self._responses:
            return {"assessment": "UNKNOWN"}
        return self._responses.pop(0)


class _HarnessOperations(Protocol):
    def prepare_request(
        self, run: Mapping[str, Any], request: Mapping[str, Any]
    ) -> dict[str, Any]: ...

    def dispatch(self, run, operation, request): ...

    def get_run(self, run_id: str) -> dict[str, Any]: ...

    def commit_event(
        self,
        run_id: str,
        *,
        expected_revision: int,
        event: Mapping[str, Any],
        state_updates: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class _ExploreGraphState(TypedDict, total=False):
    run: dict[str, Any]
    run_id: str
    problem: str
    round: int
    max_model_calls: int
    max_explore_rounds: int
    model_port: ModelPort
    call_reserved: bool
    reply: Mapping[str, Any]
    unfulfilled: str
    assessment: str
    next_phase: str
    next_action: str


def run_exploration(
    harness: _HarnessOperations,
    run: dict[str, Any],
    *,
    problem: str,
    model_port: ModelPort,
    max_model_calls: int,
    max_explore_rounds: int,
    max_runtime_seconds: int,
) -> dict[str, Any]:
    """Run the bounded Explore loop and persist every call and route decision."""

    run_id = run["run_id"]

    def reserve_call(state: _ExploreGraphState) -> dict[str, Any]:
        latest = harness.get_run(state["run_id"])
        revision = latest["state_revision"]
        counters = dict(latest["state"].get("counters", {}))
        model_calls = counters.get("model_calls", 0)
        from .budget import budget_reason

        reason = budget_reason(latest["state"], {"max_model_calls": state["max_model_calls"],
                                               "max_total_duration_seconds": max_runtime_seconds})
        if reason is not None:
            exhausted = harness.commit_event(
                state["run_id"],
                expected_revision=revision,
                event={
                    "event_id": f"explore-budget-exhausted-{revision}",
                    "type": "budget_exhausted",
                    "reason": reason,
                    "summary": "Explore stopped before dispatch because the budget was exhausted",
                },
                state_updates={
                    "phase": "TERMINAL",
                    "status": "partial_budget_exhausted",
                    "budget": {**latest["state"].get("budget", {}), "exhaustion_reason": reason},
                    "final_response": "Budget exhausted before completing solution review; no verified answer is available.",
                },
            )
            return {"call_reserved": False, "run": exhausted}

        counters["model_calls"] = model_calls + 1
        round_number = state["round"]
        reserved = harness.commit_event(
            state["run_id"],
            expected_revision=revision,
            event={
                "event_id": f"explore-dispatched-{round_number}",
                "type": "explore_dispatched",
                "round": round_number,
                "summary": f"Explore round {round_number} dispatched",
            },
            state_updates={"phase": "EXPLORE", "counters": counters},
        )
        return {"call_reserved": True, "run": reserved}

    def call_explore(state: _ExploreGraphState) -> dict[str, Any]:
        current = state["run"]
        request = {
            "run_id": state["run_id"],
            "call_id": f"{state['run_id']}:explore:{state['round']}",
            "role": "explore",
            "session_key": f"explore:{state['run_id']}:{state['round']}",
            "preplan_hint": current["state"].get("preplan_hint"),
            "round": state["round"],
            "problem": state["problem"],
            "state_revision": current["state_revision"],
        }
        guidance_task = current["state"].get("pending_guidance_task")
        if isinstance(guidance_task, str) and guidance_task.strip():
            request["specific_task"] = guidance_task
        from .calls import CallInterrupted

        from . import protocol_repair

        successful_request = request
        try:
            reply = harness.dispatch(current, state["model_port"].complete, request)
        except CallInterrupted as exc:
            current = protocol_repair.reserve_repair(
                harness, state["run_id"], exc,
                failure_event=lambda latest, failed: {
                    "event_id": f"explore-parse-{latest['state_revision']}",
                    "type": "explore_parse_failed", "call_id": failed["call_id"],
                    "summary": "Explore reply failed the response protocol; one bounded repair follows",
                },
                dispatch_event={
                    "event_id": f"explore-dispatched-{state['round']}-repair-1",
                    "type": "explore_dispatched", "round": state["round"], "role": "explore",
                    "summary": f"Explore round {state['round']} repair dispatched",
                },
            )
            successful_request = protocol_repair.repair_request(
                request, instruction=(
                    "The previous reply was complete but not valid protocol JSON. "
                    "Re-issue the exploration assessment as one strict JSON object "
                    "matching the schema; escape every backslash inside code strings."
                ))
            reply = harness.dispatch(current, state["model_port"].complete, successful_request)
        run = harness.get_run(state["run_id"])
        from .verifier_compute import continue_review

        def reserve_and_dispatch(reserved, seq, _continuation_call_id, continuation_request):
            committed = harness.commit_event(
                state["run_id"],
                expected_revision=reserved["state_revision"],
                event={
                    "event_id": f"explore-dispatched-{state['round']}-compute-{seq + 1}",
                    "type": "explore_dispatched",
                    "round": state["round"],
                    "role": "explore",
                    "summary": f"Explore round {state['round']} computation "
                               f"continuation {seq + 1} dispatched",
                },
                state_updates={
                    "counters": {
                        **reserved["state"]["counters"],
                        "model_calls": reserved["state"]["counters"]["model_calls"] + 1,
                    },
                },
            )
            continuation_reply = harness.dispatch(
                committed, state["model_port"].complete, continuation_request)
            return harness.get_run(state["run_id"]), continuation_reply

        # A declared computation runs on the shared #75 precheck path and the real
        # receipt continues this same exploration session; a pending or refused
        # request never lets the paired assessment stand.
        run, reply, unfulfilled = continue_review(
            harness, run, role="explore", step_id=None, round_number=state["round"],
            attempt_index=int(run["state"].get("attempt_index") or 0),
            base_call_id=successful_request["call_id"], base_request=successful_request,
            reply=reply, reserve_and_dispatch=reserve_and_dispatch, receipt_prefix="explore-tool")
        return {
            "run": run,
            "reply": None if unfulfilled else reply,
            "unfulfilled": "explore_tool_request_unfulfilled" if unfulfilled else None,
        }

    def persist_assessment(state: _ExploreGraphState) -> dict[str, Any]:
        assessment_data = _normalize_assessment(state.get("reply", {}))
        assessment = assessment_data["assessment"]
        round_number = state["round"]
        if assessment == "SOLVED":
            next_phase = "EXPLORE_REVIEW"
        elif assessment == "PARTIALLY_SOLVED" and round_number < state["max_explore_rounds"]:
            next_phase = "EXPLORE"
        else:
            next_phase = "PLAN"

        latest = harness.get_run(state["run_id"])
        from .verifier_compute import verifier_receipts

        receipts = verifier_receipts(
            latest["state"], role="explore", step_id=None, round_number=round_number,
            attempt_index=int(latest["state"].get("attempt_index") or 0))
        unfulfilled = state.get("unfulfilled")
        findings = list(latest["state"].get("exploration_findings", []))
        finding = {"round": round_number, **assessment_data}
        if receipts or unfulfilled:
            # Computed exploration stays unverified exploration: the record keeps
            # its provenance and never mints a ledger-grade evidence claim.
            finding["provenance"] = "unverified_exploration"
            finding["computation"] = {
                "provenance": "unverified_exploration",
                "scope": "finite_computation",
                "receipts": [
                    {
                        "receipt_id": receipt.get("receipt_id"),
                        "tool": receipt.get("tool"),
                        "status": receipt.get("status"),
                        "executed": receipt.get("executed") is True,
                        "output": receipt.get("output"),
                        "assertion_matched": receipt.get("assertion_matched") is True,
                        "comparison_status": receipt.get("comparison_status", "not_compared"),
                        "output_available": receipt.get("output_available", False),
                        "unknown_outcome": receipt.get("unknown_outcome") is True,
                    }
                    for receipt in receipts
                ],
                **({"unfulfilled": unfulfilled} if unfulfilled else {}),
            }
        findings.append(finding)
        committed = harness.commit_event(
            state["run_id"],
            expected_revision=latest["state_revision"],
            event={
                "event_id": f"explore-assessed-{round_number}",
                "type": "explore_assessed",
                "assessment": assessment,
                "round": round_number,
                "next_phase": next_phase,
                **({"unfulfilled": unfulfilled} if unfulfilled else {}),
                "summary": f"Explore round {round_number} assessed as {assessment}; next phase {next_phase}",
            },
            state_updates={"phase": next_phase, "exploration_findings": findings},
        )
        next_action = (
            "retry"
            if assessment == "PARTIALLY_SOLVED" and round_number < state["max_explore_rounds"]
            else "stop"
        )
        return {
            "run": committed,
            "assessment": assessment,
            "next_phase": next_phase,
            "next_action": next_action,
            "round": round_number + 1,
        }

    graph = StateGraph(_ExploreGraphState)
    graph.add_node("reserve_call", reserve_call)
    graph.add_node("call_explore", call_explore)
    graph.add_node("persist_assessment", persist_assessment)
    graph.add_edge(START, "reserve_call")
    graph.add_conditional_edges(
        "reserve_call",
        lambda state: "call" if state["call_reserved"] else "stop",
        {"call": "call_explore", "stop": END},
    )
    graph.add_edge("call_explore", "persist_assessment")
    graph.add_conditional_edges(
        "persist_assessment",
        lambda state: state["next_action"],
        {"retry": "reserve_call", "stop": END},
    )

    findings = run["state"].get("exploration_findings", [])
    initial: _ExploreGraphState = {
        "run": run,
        "run_id": run_id,
        "problem": problem,
        "round": len(findings) + 1,
        "max_model_calls": max_model_calls,
        "max_explore_rounds": max_explore_rounds,
        "model_port": model_port,
        "call_reserved": False,
    }
    graph.compile().invoke(initial)
    return harness.get_run(run_id)


def _normalize_assessment(reply: Any) -> dict[str, Any]:
    if not isinstance(reply, Mapping):
        return {"assessment": "UNKNOWN"}
    assessment = reply.get("assessment")
    if not isinstance(assessment, str) or assessment not in _ASSESSMENTS:
        assessment = "UNKNOWN"
    normalized: dict[str, Any] = {"assessment": assessment}
    for field in ("worked", "failed", "candidates"):
        values = reply.get(field, [])
        if isinstance(values, list):
            normalized[field] = [item for item in values if isinstance(item, str)]
    candidate = reply.get("solution_candidate")
    if isinstance(candidate, str):
        normalized["solution_candidate"] = candidate
    return normalized
