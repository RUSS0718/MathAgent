"""Deterministic APRS ordering inside persistent, fair dispatch rounds."""

from copy import deepcopy

from .aprs import _hash, pareto_set

POLICY_VERSION = "concurrent-aprs-v1"
EXECUTABLE = frozenset({"eligible", "active"})


def _rating(inputs):
    evaluations = []
    for rid, item in sorted(inputs.items()):
        cost = item.get("costs", {})
        evaluations.append({"route_id": rid, "hard_gate": True, "vector": {
            "verified_gain": len(set(item.get("produced", []))),
            "evidence_quality": item.get("evidence_quality", 0),
            "novelty": item.get("novelty", 0),
            "cost": cost.get("tokens"), "http_attempts": cost.get("http_attempts"),
            "tool_calls": cost.get("tool_calls"), "wall_time_seconds": cost.get("time_seconds"),
        }})
    order, fronts = [], []
    remaining = list(evaluations)
    while remaining:
        front = pareto_set(remaining)
        fronts.append(front)
        by_id = {item["route_id"]: item["vector"] for item in remaining}
        order.extend(sorted(front, key=lambda rid: (
            -by_id[rid]["verified_gain"], -by_id[rid]["evidence_quality"],
            -by_id[rid]["novelty"],
            *[part for field in ("cost", "http_attempts", "tool_calls", "wall_time_seconds")
              for part in (by_id[rid][field] is None, by_id[rid][field] or 0)], rid,
        )))
        remaining = [item for item in remaining if item["route_id"] not in front]
    return {"policy_version": POLICY_VERSION, "inputs": deepcopy(inputs),
            "input_hash": _hash(inputs), "evaluations": evaluations,
            "pareto_fronts": fronts, "order": order}


def replay_rating(record):
    """Recompute inputs and output; a stored replay flag is never authoritative."""
    return isinstance(record, dict) and record == _rating(record.get("inputs", {}))


def round_schedule(population):
    """Freeze eligible members; completed dispatch opportunities advance a round."""
    routes = population.get("routes", {})
    members = list(population.get("round_members", []))
    opportunities = list(population.get("opportunities", []))
    # A member that cannot execute has an explicit exit from this round. Waiting
    # actions already received their opportunity; their eventual return is separate.
    exits = [rid for rid in members
             if rid not in opportunities and routes.get(rid, {}).get("status") not in EXECUTABLE]
    opportunities.extend(exits)
    number = population.get("round", 0)
    if not members or set(members) <= set(opportunities):
        members = sorted(
            rid for rid, item in routes.items()
            if item.get("status") in EXECUTABLE and not item.get("inflight_action_id")
        )
        opportunities = []
        if members:
            number += 1
    inputs = {rid: {key: deepcopy(routes[rid].get(key, default)) for key, default in (
        ("produced", []), ("adopted", []), ("costs", {}),
        ("evidence_quality", 0), ("novelty", 0),
    )} for rid in members if rid not in opportunities}
    rating = _rating(inputs)
    return {"round": number, "round_members": members, "opportunities": opportunities,
            "order": rating["order"], "rating": rating}
