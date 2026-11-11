"""Read-only route projection; never export private Rater input snapshots."""
import hashlib
import json
import math

from .aprs import replay_decision

RESOURCE_KEYS = ("model_calls", "logical_calls", "http_attempts", "tokens", "charged_tokens",
                 "reserved_tokens", "tool_calls", "tool_wall_time_seconds", "wall_time_seconds")


def _numbers(value, keys):
    return {key: number if type(number) in (int, float) and math.isfinite(number) and number >= 0 else None
            for key in keys if key in value for number in [value[key]]}


def route_summary(state):
    """Project finite numeric vectors and independently verify persisted decisions."""
    groups = state.get("route_evaluations", [])
    latest = {}
    routes = {item["route_id"]: item for item in state.get("route_registry", [])}
    by_hash = {}
    for group in groups:
        evaluations = group.get("evaluations", [])
        digest = hashlib.sha256(json.dumps(sorted(evaluations, key=lambda item: item["route_id"]),
                                          ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        by_hash[digest] = evaluations
        for item in evaluations:
            latest[item["route_id"]] = item
    decisions = []
    for item in state.get("aprs_decisions", []):
        public = {key: item.get(key) for key in (
            "state_revision", "selected_route_id", "pareto_route_ids", "reason", "policy_version") if key in item}
        matched = by_hash.get(item.get("evaluation_hash"))
        public["replayable"] = matched is not None and replay_decision(matched, item)
        decisions.append(public)
    budget = state.get("route_budget", {})
    snapshot = budget.get("current_snapshot") or {}
    def current(item):
        route = routes.get(item["route_id"], {})
        return (not route.get("needs_reevaluation")
                and item.get("snapshot", {}).get("route_status") == route.get("status")
                and item.get("snapshot", {}).get("graph_version")
                == (state.get("proof_graph") or {}).get("current_version", route.get("graph_version")))

    return {
        "policy_version": state["route_policy"].get("policy_version"),
        "active_route_id": state.get("active_route_id"),
        "items": [{key: item.get(key) for key in (
            "route_id", "parent_route_id", "kind", "status", "frontier_digest", "graph_version",
            "policy_version", "stop_reason", "elimination_reason", "needs_reevaluation") if key in item}
            for item in state.get("route_registry", [])],
        "decisions": decisions,
        "evaluations": [{
            "route_id": key, "input_hash": item.get("input_hash"), "current": current(item),
            "hard_gate": current(item) and item.get("hard_gate") is True,
            "memory_hits": [{field: hit[field] for field in (
                "record_id", "source_run_id", "outcome", "use", "review_status", "authority",
                "imported_from",
            ) if field in hit} for hit in item.get("snapshot", {}).get("memory_hits", [])
                if isinstance(hit, dict)],
            "population_memory_cost": {
                key: value for key, value in item.get("snapshot", {}).get(
                    "population_memory_cost", {}
                ).items() if key in {
                    "status", "call_count", "estimated_tokens", "additional_utf8_bytes",
                    "estimator_versions",
                }
            },
            "vector": {**_numbers(item.get("vector", {}), (
                "verified_gain", "evidence_quality", "novelty", "cost", "http_attempts", "tool_calls", "wall_time_seconds")),
                       "cost_known": item.get("vector", {}).get("cost_known") is True},
        } for key, item in sorted(latest.items())],
        "budget": {"closing_reserve": _numbers(budget.get("closing_reserve", {}), RESOURCE_KEYS),
                   "remaining": _numbers(budget.get("remaining", {}), RESOURCE_KEYS),
                   "accounting": _numbers(snapshot, RESOURCE_KEYS),
                   "unknown": bool(snapshot.get("unknown_attempts") or snapshot.get("unresolved_attempts")
                                   or snapshot.get("unknown_tool_calls")),
                   "has_reservations": bool(snapshot.get("reserved_tokens"))},
    }
