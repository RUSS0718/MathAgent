"""Deterministic Rater/Pareto/APRS decisions for the serial route mode."""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from typing import Any

from .routes import POLICY_VERSION

_ROUTE_COST_FIELDS = (
    "charged_tokens", "logical_calls", "http_attempts", "tool_calls",
    "tool_wall_time_seconds", "wall_time_seconds",
)
_ROUTE_STOP_STATES = {"stalled", "completed", "terminated", "pruned"}


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def replay_decision(evaluations, decision):
    """Validate persisted decision inputs before claiming replay success."""
    if not _valid_evaluations(evaluations):
        return False
    policy = decision.get("policy_version")
    if policy != POLICY_VERSION:
        return False
    frozen = decision.get("decision_input")
    if not isinstance(frozen, dict) or decision.get("decision_input_hash") != _hash(frozen):
        return False
    expected = _choose({"route_policy": {"policy_version": policy}}, evaluations,
                       stop_reason=frozen.get("stop_reason"))
    return all(decision.get(key) == value for key, value in expected.items())


def _graph_source_current(state, evidence):
    """A linked graph attempt must still support its unconflicted proposition."""
    graph = state.get("proof_graph")
    if not isinstance(graph, dict):
        return True
    snapshot = next((item for item in graph.get("snapshots", [])
                     if item.get("graph_version") == graph.get("current_version")), None)
    if snapshot is None:
        return False
    records = [item for item in state.get("verified_results_ledger", [])
           if item.get("source") == evidence.get("source")
           and ("result_id" not in evidence or item.get("result_id") == evidence["result_id"])
           and all(key not in evidence or item.get(key) == evidence[key]
                   for key in ("plan_version", "attempt_index", "review_call_id"))
           and set(item.get("claim_indexes", [])).intersection(evidence.get("claim_indexes", []))]
    for index in evidence.get("claim_indexes", []):
        ids = {item.get("result_id") for item in records if index in item.get("claim_indexes", [])}
        linked = [item for item in snapshot.get("attempts", {}).values() if item.get("result_id") in ids]
        # S03 obligation evidence need not have a classified F1 graph node.
        if linked and not any(
            item.get("status") == "accepted" and item.get("direction", "support") == "support"
            and snapshot.get("propositions", {}).get(item.get("conclusion"), {}).get("status") == "supported"
            and not snapshot["propositions"][item["conclusion"]].get("conflict") for item in linked
        ):
            return False
    return True


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
        and _graph_source_current(state, item)
    }
    credit = set(
        obligation_id for obligation_id, item in ledger.items()
        if item.get("status") == "satisfied"
        and any(ref in evidence for ref in item.get("evidence_refs", []))
    )
    from .progress import prerequisite_goals

    relevant = set().union(*prerequisite_goals(state).values())
    for step in (state.get("plan") or {}).get("steps", []):
        record = state.get("steps", {}).get(step.get("step_id"), {})
        review = record.get("verification") or {}
        if review.get("valid") is not True or review.get("verdict") != "ACCEPT":
            continue
        goals = {item["goal_id"]: item for item in state.get("problem_spec", {}).get("auxiliary_goals", [])}
        for goal_id in relevant.intersection(step.get("auxiliary_goal_ids", [])):
            statement = goals.get(goal_id, {}).get("statement")
            if not statement:
                continue
            for record in state.get("verified_results_ledger", []):
                if (record.get("source") == step.get("step_id")
                        and record.get("statement") == statement
                        and record.get("valid") is True and record.get("proven") is True
                        and record.get("invalidated") is not True
                        and record.get("category") != "Conjecture"
                        and record.get("claim_indexes")
                        and all(key not in state or record.get(key) == state[key]
                                for key in ("plan_version", "attempt_index"))
                        and _graph_source_current(state, record)):
                    credit.add(goal_id)
                    break
    return sorted(credit)


def _route_cost_delta(start, end):
    """Compute only costs proven by both route-boundary ledger snapshots."""
    costs = {}
    if not isinstance(start, dict) or not isinstance(end, dict):
        return {key: None for key in _ROUTE_COST_FIELDS}
    if not any(key in start for key in _ROUTE_COST_FIELDS):
        return {key: None for key in _ROUTE_COST_FIELDS}
    unknown = False
    for key in ("unknown_attempts", "unresolved_attempts", "unknown_tool_calls", "reserved_tokens"):
        before, after = start.get(key, 0), end.get(key, 0)
        if (type(before) not in (int, float) or type(after) not in (int, float)
                or not math.isfinite(before) or not math.isfinite(after) or after > before):
            unknown = True
    before_unknown = start.get("provider_unknown_fields", {})
    after_unknown = end.get("provider_unknown_fields", {})
    if isinstance(before_unknown, dict) and isinstance(after_unknown, dict):
        for key, count in after_unknown.items():
            prior = before_unknown.get(key, 0)
            if (type(prior) is not int or type(count) is not int or count > prior):
                unknown = True
    elif before_unknown or after_unknown:
        unknown = True
    for key in _ROUTE_COST_FIELDS:
        before, after = start.get(key), end.get(key)
        if (type(before) in (int, float) and type(after) in (int, float)
                and math.isfinite(before) and math.isfinite(after)
                and before >= 0 and after >= before):
            costs[key] = after - before
        else:
            costs[key] = None
    return {key: None for key in _ROUTE_COST_FIELDS} if unknown else costs


def _frozen_route_snapshot(state, route_id):
    """Find the first persisted APRS input recorded after this route stopped."""
    for group in state.get("route_evaluations", []):
        for evaluation in group.get("evaluations", []):
            snapshot = evaluation.get("snapshot")
            if (isinstance(snapshot, dict) and snapshot.get("route_id") == route_id
                    and snapshot.get("route_status") in _ROUTE_STOP_STATES):
                return snapshot
    return None


def _memory_hits(state):
    """Keep bounded source identity for advisory hits, without their content."""
    advisory = state.get("population_memory_advisory")
    if not isinstance(advisory, dict) or advisory.get("authority") != "advisory_only":
        return []
    hits = []
    for item in advisory.get("observations", []):
        if not isinstance(item, dict) or not isinstance(item.get("record_id"), str):
            continue
        provenance = item.get("provenance")
        source_run_id = provenance.get("source_run_id") if isinstance(provenance, dict) else None
        if not isinstance(source_run_id, str) or not source_run_id:
            continue
        hit = {
            "record_id": item["record_id"],
            "source_run_id": source_run_id,
            "outcome": item.get("outcome"),
            "use": item.get("use"),
            "review_status": item.get("review_status"),
            "authority": "advisory_only",
        }
        imported = provenance.get("imported_from")
        if isinstance(imported, dict) and isinstance(imported.get("record_id"), str):
            hit["imported_from"] = {"record_id": imported["record_id"]}
        hits.append(hit)
    return hits


def _population_memory_cost(state, route_id):
    """Aggregate only this route's prompt-size estimates, preserving unknowns."""
    records = [
        call["population_memory_cost"]
        for call in state.get("calls", {}).values()
        if isinstance(call, dict) and call.get("route_id") == route_id
        and isinstance(call.get("population_memory_cost"), dict)
    ]
    base = {
        "status": "not_injected" if not records else "estimated",
        "call_count": len(records),
        "estimated_tokens": 0 if not records else None,
        "additional_utf8_bytes": 0 if not records else None,
        "estimator_versions": sorted({
            item["estimator_version"] for item in records
            if isinstance(item.get("estimator_version"), str)
        }),
    }
    if not records:
        advisory = state.get("population_memory_advisory")
        if (isinstance(advisory, dict) and advisory.get("authority") == "advisory_only"
                and advisory.get("observations")):
            return {**base, "status": "unknown", "estimated_tokens": None,
                    "additional_utf8_bytes": None}
        return base
    if any(
        item.get("status") != "estimated"
        or type(item.get("estimated_tokens")) is not int
        or item["estimated_tokens"] < 0
        or type(item.get("additional_utf8_bytes")) is not int
        or item["additional_utf8_bytes"] < 0
        or not isinstance(item.get("estimator_version"), str)
        for item in records
    ) or len(base["estimator_versions"]) != 1:
        return {**base, "status": "unknown"}
    return {
        **base,
        "estimated_tokens": sum(item["estimated_tokens"] for item in records),
        "additional_utf8_bytes": sum(item["additional_utf8_bytes"] for item in records),
    }


def rater_snapshot(state: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    current_credit = verified_gain(state)
    gain = sorted(set(current_credit) - set(route.get("credit_at_start", [])))
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
    baseline = route.get("budget_at_start") or {}
    frozen = _frozen_route_snapshot(state, route.get("route_id"))
    costs = (deepcopy(frozen.get("consumed_resources", {})) if frozen is not None
             else _route_cost_delta(baseline, budget))
    actual_cost = costs["charged_tokens"]
    return {
        "run_id": state.get("run_id"),
        "state_revision": state.get("state_revision"),
        "graph_version": (state.get("proof_graph") or {}).get("current_version", route.get("graph_version")),
        "route_id": route.get("route_id"),
        "frontier_digest": route.get("frontier_digest"),
        "root_obligations": deepcopy(state.get("obligation_ledger") or []),
        "verified_gain": gain,
        "current_credit": current_credit,
        "evidence_quality": len(gain),
        "novelty": len(current_objectives - prior_objectives),
        "cost_known": actual_cost is not None,
        "actual_cost": actual_cost,
        "consumed_resources": costs,
        "cost_basis": "frozen_route_boundary" if frozen is not None else "route_delta",
        "route_status": route.get("status"),
        "needs_reevaluation": route.get("needs_reevaluation") is True,
        "unknown_observations": deepcopy(route.get("unknown_observations") or []),
        "remaining_budget": deepcopy(budget),
        "closing_reserve": deepcopy(state.get("route_budget", {}).get("closing_reserve") or {}),
        "policy_version": state.get("route_policy", {}).get("policy_version", POLICY_VERSION),
        "memory_hits": _memory_hits(state),
        "population_memory_cost": _population_memory_cost(state, route.get("route_id")),
    }


def _evaluate_snapshot(snapshot):
    """Recompute all decision fields solely from a frozen persisted input."""
    vector = {
        "verified_gain": len(snapshot["verified_gain"]),
        "evidence_quality": snapshot["evidence_quality"],
        "novelty": snapshot["novelty"],
        "cost": snapshot["actual_cost"],
        "cost_known": snapshot["cost_known"],
        "http_attempts": snapshot["consumed_resources"].get("http_attempts"),
        "tool_calls": snapshot["consumed_resources"].get("tool_calls"),
        "wall_time_seconds": snapshot["consumed_resources"].get("wall_time_seconds"),
        "unknown_attempts": snapshot["remaining_budget"].get("unknown_attempts"),
    }
    return {"route_id": snapshot["route_id"], "vector": vector,
            "input_hash": _hash(snapshot), "policy_version": snapshot["policy_version"],
            "hard_gate": snapshot["needs_reevaluation"] is not True
            and snapshot["route_status"] in {"created", "eligible", "active"},
            "snapshot": snapshot}


def evaluate(state: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    return _evaluate_snapshot(rater_snapshot(state, route))


def _valid_evaluations(evaluations):
    try:
        return (len({item["route_id"] for item in evaluations}) == len(evaluations)
                and all(item == _evaluate_snapshot(item["snapshot"])
                        and item["policy_version"] == POLICY_VERSION for item in evaluations))
    except (KeyError, TypeError, ValueError):
        return False


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
                if (other_cost is None) != (candidate_cost is None):
                    return False
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


def _choose(state: dict[str, Any], evaluations: list[dict[str, Any]], *, stop_reason: str | None = None) -> dict[str, Any]:
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
    frozen = {"stop_reason": stop_reason}
    return {"selected_route_id": selected, "candidate_route_ids": sorted(eligible),
            "pareto_route_ids": pareto, "reason": reason,
            "policy_version": state.get("route_policy", {}).get("policy_version", POLICY_VERSION),
            "evaluation_hash": _hash(sorted(evaluations, key=lambda item: item["route_id"])),
            "decision_input": frozen, "decision_input_hash": _hash(frozen)}


def decide(state: dict[str, Any], evaluations: list[dict[str, Any]], *, stop_reason: str | None = None) -> dict[str, Any]:
    decision = _choose(state, evaluations, stop_reason=stop_reason)
    decision["replayable"] = replay_decision(evaluations, decision)
    return decision


def rate_routes(state: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    evaluations = [evaluate(state, route) for route in state.get("route_registry", [])]
    return evaluations, decide(state, evaluations)
