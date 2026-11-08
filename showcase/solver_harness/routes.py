"""Opt-in serial CandidateRoute lineage and frontier accounting."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

POLICY_VERSION = "serial-aprs-v1"
ROUTE_STATES = frozenset({"created", "eligible", "active", "stalled", "completed", "terminated", "pruned"})


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def frontier_digest(frontier: Any) -> str:
    """Hash a normalized frontier; ordering and duplicate goals are immaterial."""
    if not isinstance(frontier, list):
        frontier = []
    normalized = sorted({_canonical(item) for item in frontier})
    return hashlib.sha256(_canonical(normalized).encode("utf-8")).hexdigest()


def validate_route_frontier(state: dict[str, Any], plan: Any) -> str | None:
    """Validate a proposed route before it can be persisted or executed."""
    if state.get("route_policy", {}).get("enabled") is not True:
        return None
    frontier = plan_frontier(plan, state.get("problem_spec"))
    if not frontier:
        return "empty_route_frontier"
    digest = frontier_digest(frontier)
    if any(item.get("frontier_digest") == digest for item in state.get("route_registry", [])):
        return "duplicate_route_frontier"
    routes = state.get("route_registry", [])
    if routes:
        active = next((item for item in routes if item.get("route_id") == state.get("active_route_id")), None)
        if active is None or active.get("kind") != "primary" or active.get("status") != "stalled":
            return "alternate_requires_stalled_primary"
        progress = state.get("progress", {})
        if progress.get("trigger") not in {"stagnation", "local_action_blocked"}:
            return "route_switch_requires_s04_stagnation"
    route_budget = state.get("route_budget", {})
    if route_budget.get("expansion_allowed") is False:
        return "route_expansion_budget_reserved"
    if state.get("budget", {}).get("exhaustion_reason"):
        return "route_expansion_budget_exhausted"
    if any(item.get("kind") == "alternate" for item in routes):
        return "alternate_route_limit_reached"
    return None


def validate_route_state_patch(previous: dict[str, Any], event: dict[str, Any], updates: dict[str, Any]) -> None:
    """Validate route history shape inside the SolverStateStore CAS transaction."""
    if "route_policy" in updates:
        raise ValueError("route_policy_is_run_frozen")
    old_routes = previous.get("route_registry", [])
    new_routes = updates.get("route_registry")
    if new_routes is None:
        return
    if not isinstance(new_routes, list) or new_routes[:len(old_routes)] != old_routes:
        # A route transition may copy the list, but cannot rewrite an existing route.
        if event.get("type") != "route_created" and event.get("route_invalidation") is None:
            raise ValueError("route_history_rewrite")
    old_lineage = previous.get("route_lineage", [])
    new_lineage = updates.get("route_lineage", old_lineage)
    if not isinstance(new_lineage, list) or new_lineage[:len(old_lineage)] != old_lineage:
        raise ValueError("route_lineage_rewrite")
    if event.get("type") == "route_created":
        added = [item for item in new_routes if item not in old_routes]
        if len(added) != 1 or added[0].get("route_id") != event.get("route_id"):
            raise ValueError("route_creation_mismatch")


def plan_frontier(plan: Any, specification: Any = None) -> list[dict[str, Any]]:
    if not isinstance(plan, dict):
        return []
    objective_ids = set()
    for step in plan.get("steps", []):
        if not isinstance(step, dict):
            continue
        objective_ids.update(item for item in step.get("obligation_ids", []) if isinstance(item, str))
        objective_ids.update(item for item in step.get("auxiliary_goal_ids", []) if isinstance(item, str))
    # A frontier is the set of frozen specification objectives, never plan
    # labels or prose. Without a ProblemSpec, an unlabeled legacy plan has no
    # trustworthy mathematical frontier to expose.
    if not isinstance(specification, dict):
        return [{"objective_id": item} for item in sorted(objective_ids)]
    known = {
        item.get("obligation_id") for item in specification.get("root_obligations", [])
        if isinstance(item, dict)
    } | {
        item.get("goal_id") for item in specification.get("auxiliary_goals", [])
        if isinstance(item, dict)
    }
    return [{"objective_id": item} for item in sorted(objective_ids & known)]


def _route_id(routes: list[dict[str, Any]], parent: str | None, digest: str) -> str:
    seed = f"{parent or 'root'}:{digest}:{len(routes)}"
    return "route_" + hashlib.sha256(seed.encode()).hexdigest()[:20]


def register_route(
    state: dict[str, Any],
    *,
    frontier: list[dict[str, Any]],
    graph_version: int | None = None,
    parent_route_id: str | None = None,
    kind: str = "primary",
    mutation: dict[str, Any] | None = None,
    state_revision: int = 0,
) -> dict[str, Any]:
    """Return a route patch, rejecting equivalent frontiers and excess alternates."""
    routes = deepcopy(state.get("route_registry") or [])
    digest = frontier_digest(frontier)
    if any(item.get("frontier_digest") == digest for item in routes):
        raise ValueError("duplicate_route_frontier")
    if kind == "alternate":
        primary = next((item for item in routes if item.get("kind") == "primary"), None)
        if primary is None or primary.get("status") != "stalled":
            raise ValueError("alternate_requires_stalled_primary")
        if any(item.get("kind") == "alternate" for item in routes):
            raise ValueError("alternate_route_limit_reached")
    if kind not in {"primary", "alternate"}:
        raise ValueError("route_kind_invalid")
    route_id = _route_id(routes, parent_route_id, digest)
    route = {
        "route_id": route_id,
        "parent_route_id": parent_route_id,
        "kind": kind,
        "status": "created",
        "frontier": deepcopy(frontier),
        "frontier_digest": digest,
        "graph_version": graph_version,
        "policy_version": state.get("route_policy", {}).get("policy_version", POLICY_VERSION),
        "mutation": deepcopy(mutation) if isinstance(mutation, dict) else None,
        "stop_reason": None,
        "elimination_reason": None,
        "created_revision": state_revision,
        "verified_gain": [],
        "unknown_observations": [],
    }
    lineage = deepcopy(state.get("route_lineage") or [])
    lineage.append({"event": "route_created", "route_id": route_id,
                    "parent_route_id": parent_route_id, "kind": kind,
                    "frontier_digest": digest, "reason": None})
    return {"route_registry": [*routes, route], "route_lineage": lineage,
            "active_route_id": route_id}


def transition_route(state: dict[str, Any], route_id: str, status: str, *, reason: str | None = None) -> dict[str, Any]:
    if status not in ROUTE_STATES:
        raise ValueError("route_status_invalid")
    routes = deepcopy(state.get("route_registry") or [])
    route = next((item for item in routes if item.get("route_id") == route_id), None)
    if route is None:
        raise ValueError("route_not_found")
    route["status"] = status
    if status in {"stalled", "completed", "terminated"}:
        route["stop_reason"] = reason
    if status == "pruned":
        route["elimination_reason"] = reason
    lineage = deepcopy(state.get("route_lineage") or [])
    lineage.append({"event": "route_transition", "route_id": route_id,
                    "status": status, "reason": reason})
    return {"route_registry": routes, "route_lineage": lineage,
            "active_route_id": route_id if status in {"created", "eligible", "active"} else state.get("active_route_id")}


def invalidate_routes(state: dict[str, Any], graph_version: int | None) -> dict[str, Any]:
    """Mark routes from an old graph as requiring re-evaluation; retain history."""
    routes = deepcopy(state.get("route_registry") or [])
    changed = []
    for route in routes:
        if graph_version is not None and route.get("graph_version") not in {None, graph_version}:
            route["needs_reevaluation"] = True
            changed.append(route["route_id"])
    return {"route_registry": routes, "route_invalidations": [
        *state.get("route_invalidations", []),
        {"graph_version": graph_version, "route_ids": changed},
    ]} if changed else {}


def sync_plan_route(harness, run: dict[str, Any]) -> dict[str, Any]:
    """Persist one route registration at a plan boundary; never dispatches work."""
    state = run["state"]
    if state.get("route_policy", {}).get("enabled") is not True:
        return run
    frontier = plan_frontier(state.get("plan"), state.get("problem_spec"))
    if not frontier:
        return run
    digest = frontier_digest(frontier)
    routes = state.get("route_registry") or []
    error = validate_route_frontier(state, state.get("plan"))
    if error is not None:
        return harness.commit_event(
            run["run_id"], expected_revision=run["state_revision"],
            event={"event_id": f"route-rejected-{run['state_revision']}",
                   "type": "route_rejected", "route_reason": error,
                   "policy_version": state.get("route_policy", {}).get("policy_version")},
            state_updates={"route_rejections": [*state.get("route_rejections", []), error]},
        )
    kind = "primary" if not routes else "alternate"
    parent = None
    route_state = state
    if routes:
        active = next((item for item in routes if item.get("route_id") == state.get("active_route_id")), None)
        if active is None:
            return run
        route_state = {**state, **transition_route(state, active["route_id"], "stalled", reason="plan_replaced")}
        parent = active["route_id"]
    try:
        patch = register_route(route_state, frontier=frontier,
                               graph_version=(state.get("proof_graph") or {}).get("current_version"),
                               parent_route_id=parent, kind=kind,
                               mutation={"kind": "plan_replaced"} if parent else None,
                               state_revision=run["state_revision"])
    except ValueError:
        return run
    route = patch["route_registry"][-1]
    route["status"] = "active"
    patch["route_lineage"].append({"event": "route_transition", "route_id": route["route_id"],
                                    "status": "active", "reason": "route_selected"})
    from .aprs import rate_routes

    preview = {**state, **patch}
    evaluations, decision = rate_routes(preview)
    patch["route_evaluations"] = [*state.get("route_evaluations", []),
                                   {"state_revision": run["state_revision"],
                                    "evaluations": evaluations}]
    patch["aprs_decisions"] = [*state.get("aprs_decisions", []),
                                {"state_revision": run["state_revision"], **decision}]
    return harness.commit_event(
        run["run_id"], expected_revision=run["state_revision"],
        event={"event_id": f"route-created-{run['state_revision']}-{route['route_id']}",
               "type": "route_created", "route_id": route["route_id"],
               "parent_route_id": parent, "route_kind": kind,
               "frontier_digest": digest, "route_status": "active",
               "policy_version": route["policy_version"], "route_reason": "plan_boundary",
               "route_count": len(preview["route_registry"]),
               "selected_route_id": decision.get("selected_route_id"),
               "pareto_route_ids": decision.get("pareto_route_ids", []),
               "route_replayable": decision.get("replayable") is True},
        state_updates=patch,
    )


def prepare_route_switch(harness, run: dict[str, Any]) -> dict[str, Any]:
    """Atomically mark the primary stalled immediately before alternate planning."""
    state = run["state"]
    if state.get("route_policy", {}).get("enabled") is not True:
        return run
    active = next((item for item in state.get("route_registry", [])
                   if item.get("route_id") == state.get("active_route_id")), None)
    if active is None or active.get("kind") != "primary" or active.get("status") != "active":
        return run
    if state.get("progress", {}).get("trigger") not in {"stagnation", "local_action_blocked"}:
        raise ValueError("route_switch_requires_s04_stagnation")
    patch = transition_route(state, active["route_id"], "stalled", reason="s04_stagnation")
    return harness.commit_event(
        run["run_id"], expected_revision=run["state_revision"],
        event={"event_id": f"route-stalled-{run['state_revision']}", "type": "route_transition",
               "route_id": active["route_id"], "route_status": "stalled",
               "route_reason": "s04_stagnation",
               "policy_version": state["route_policy"]["policy_version"]},
        state_updates=patch,
    )
