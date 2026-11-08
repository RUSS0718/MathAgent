"""Deterministic Rater/Pareto/APRS decisions for the serial route mode."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from .routes import POLICY_VERSION


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verified_gain(state: dict[str, Any]) -> list[str]:
    """Return current root obligation credit from valid, current evidence only."""
    version = state.get("specification_version")
    if version is None:
        version = (state.get("problem_spec") or {}).get("specification_version")
    ledger = {
        item.get("obligation_id"): item
        for item in state.get("obligation_ledger", [])
        if isinstance(item, dict)
    }
    evidence = {
        item.get("evidence_id"): item
        for item in state.get("obligation_evidence_ledger", [])
        if isinstance(item, dict)
        and item.get("valid") is True
        and item.get("invalidated") is not True
        and (version is None or item.get("specification_version") == version
             or version in item.get("applicable_specification_versions", []))
    }
    return sorted(
        obligation_id for obligation_id, item in ledger.items()
        if item.get("status") == "satisfied"
        and any(ref in evidence for ref in item.get("evidence_refs", []))
    )


def rater_snapshot(state: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    gain = verified_gain(state)
    frontier = route.get("frontier") or []
    current_objectives = {item.get("objective_id") for item in frontier if isinstance(item, dict)}
    prior_objectives = {
        item.get("objective_id")
        for other in state.get("route_registry", [])
        if other.get("route_id") != route.get("route_id")
        for item in other.get("frontier", [])
        if isinstance(item, dict)
    }
    budget = state.get("route_budget", {}).get("current_snapshot") or {}
    actual_cost = budget.get("charged_tokens")
    return {
        "run_id": state.get("run_id"),
        "state_revision": state.get("state_revision"),
        "graph_version": route.get("graph_version"),
        "route_id": route.get("route_id"),
        "frontier_digest": route.get("frontier_digest"),
        "root_obligations": deepcopy(state.get("obligation_ledger") or []),
        "verified_gain": gain,
        "evidence_quality": len(gain),
        "novelty": len(current_objectives - prior_objectives),
        "cost_known": actual_cost is not None,
        "actual_cost": actual_cost,
        "unknown_observations": deepcopy(route.get("unknown_observations") or []),
        "remaining_budget": deepcopy(budget),
        "closing_reserve": deepcopy(state.get("route_budget", {}).get("closing_reserve") or {}),
        "policy_version": state.get("route_policy", {}).get("policy_version", POLICY_VERSION),
    }


def evaluate(state: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    snapshot = rater_snapshot(state, route)
    vector = {
        "verified_gain": len(snapshot["verified_gain"]),
        "evidence_quality": snapshot["evidence_quality"],
        "novelty": snapshot["novelty"],
        "cost": snapshot["actual_cost"],
        "cost_known": snapshot["cost_known"],
        "http_attempts": snapshot["remaining_budget"].get("http_attempts"),
        "tool_calls": snapshot["remaining_budget"].get("tool_calls"),
        "wall_time_seconds": snapshot["remaining_budget"].get("wall_time_seconds"),
        "unknown_attempts": snapshot["remaining_budget"].get("unknown_attempts"),
    }
    return {"route_id": route["route_id"], "vector": vector,
            "input_hash": _hash(snapshot), "policy_version": snapshot["policy_version"],
            "hard_gate": route.get("needs_reevaluation") is not True
            and route.get("status") in {"created", "eligible", "active"},
            "snapshot": snapshot}


def pareto_set(evaluations: list[dict[str, Any]]) -> list[str]:
    valid = [item for item in evaluations if item.get("hard_gate") is True]
    result = []
    for candidate in valid:
        c = candidate["vector"]
        def no_worse(other):
            for key in ("verified_gain", "evidence_quality", "novelty"):
                if other["vector"][key] < c[key]:
                    return False
            for key in ("cost", "http_attempts", "tool_calls", "wall_time_seconds"):
                other_cost, candidate_cost = other["vector"].get(key), c.get(key)
                if other_cost is not None and candidate_cost is not None and other_cost > candidate_cost:
                    return False
            return True

        def strictly_better(other):
            better = any(other["vector"][key] > c[key]
                          for key in ("verified_gain", "evidence_quality", "novelty"))
            for key in ("cost", "http_attempts", "tool_calls", "wall_time_seconds"):
                if other["vector"].get(key) is not None and c.get(key) is not None:
                    better = better or other["vector"][key] < c[key]
            return better

        dominated = any(other["route_id"] != candidate["route_id"]
                        and no_worse(other) and strictly_better(other)
                        for other in valid)
        if not dominated:
            result.append(candidate["route_id"])
    return sorted(result)


def decide(state: dict[str, Any], evaluations: list[dict[str, Any]], *, stop_reason: str | None = None) -> dict[str, Any]:
    pareto = pareto_set(evaluations)
    eligible = {item["route_id"]: item for item in evaluations if item.get("hard_gate") is True}
    selected = None
    if pareto:
        selected = sorted(pareto, key=lambda rid: (
            -eligible[rid]["vector"]["verified_gain"],
            -eligible[rid]["vector"]["evidence_quality"],
            -eligible[rid]["vector"]["novelty"],
            eligible[rid]["vector"]["cost"] is None,
            eligible[rid]["vector"]["cost"] if eligible[rid]["vector"]["cost"] is not None else float("inf"), rid,
        ))[0]
    reason = stop_reason or ("no_eligible_route" if selected is None else "route_selected")
    return {"selected_route_id": selected, "candidate_route_ids": sorted(eligible),
            "pareto_route_ids": pareto, "reason": reason,
            "policy_version": state.get("route_policy", {}).get("policy_version", POLICY_VERSION),
            "evaluation_hash": _hash(evaluations), "replayable": True}


def rate_routes(state: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    evaluations = [evaluate(state, route) for route in state.get("route_registry", [])]
    return evaluations, decide(state, evaluations)
