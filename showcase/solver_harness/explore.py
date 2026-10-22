"""Deterministic Explore routing for the Solver Harness."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
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
        elapsed = (
            datetime.now(UTC) - datetime.fromisoformat(latest["state"]["created_at"])
        ).total_seconds()
        reason = None
        if elapsed >= max_runtime_seconds:
            reason = "runtime_budget_exhausted"
        elif model_calls >= state["max_model_calls"]:
            reason = "model_call_budget_exhausted"
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
            "round": state["round"],
            "problem": state["problem"],
            "state_revision": current["state_revision"],
        }
        return {"reply": state["model_port"].complete(harness.prepare_request(current, request))}

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
        findings = list(latest["state"].get("exploration_findings", []))
        finding = {"round": round_number, **assessment_data}
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
