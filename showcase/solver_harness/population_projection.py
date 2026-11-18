"""Safe, aggregate-only public view of concurrent route execution."""

from collections import Counter


def population_projection(state):
    population = state.get("population", {})
    routes = population.get("routes", {})
    actions = population.get("actions", {})
    members = population.get("round_members", [])
    opportunities = population.get("opportunities", [])
    statuses = Counter(route.get("status", "unknown") for route in routes.values())
    worker_slots = sum(
        action.get("reservation", {}).get("worker_slots", 1)
        for action in actions.values() if action.get("status") == "inflight"
    )
    physically_pending = {
        action_id for action_id, action in actions.items()
        if action.get("status") == "unknown"
        and action.get("settlement_status", "pending") == "pending"
    }
    unresolved_calls = [
        call for call in state.get("calls", {}).values()
        if call.get("status") in {"dispatched", "streaming", "unknown_outcome"}
        and (call.get("action_id") in physically_pending
             or actions.get(call.get("action_id"), {}).get("status") == "inflight")
    ]
    http_inflight = len(unresolved_calls)
    if not unresolved_calls:
        http_inflight = sum(
            action.get("reservation", {}).get("http_inflight", 0)
            or (action.get("reservation", {}).get("http_attempts", 1)
                if action_id in physically_pending else 0)
            for action_id, action in actions.items()
        )
    return {
        "version": population.get("schema_version", "population-v1"),
        "scheduler": {
            "round": population.get("round", 0),
            "member_count": len(members),
            "opportunities_used": len(opportunities),
            "verified_gain_count": sum(
                item.get("status") == "satisfied"
                for item in state.get("obligation_ledger", [])
            ),
            "route_counts": dict(sorted(statuses.items())),
            "paused": bool(population.get("paused_reason")),
        },
        "resources": {
            "worker_slots_in_use": worker_slots,
            "http_inflight": http_inflight,
            "unknown_routes": sum(action.get("status") == "unknown" for action in actions.values()),
            "unknown_requests": len(physically_pending),
        },
        "delivery": {key: population.get("delivery", {}).get(key)
                     for key in ("status", "reason") if key in population.get("delivery", {})},
        "settlement": {key: population.get("settlement", {}).get(key)
                       for key in ("status", "unknown_count")
                       if key in population.get("settlement", {})},
    }
