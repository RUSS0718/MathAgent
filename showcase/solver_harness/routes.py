"""Opt-in serial CandidateRoute lineage and frontier accounting."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from .progress import normalize_method

POLICY_VERSION = "serial-aprs-v1"
ROUTE_STATES = frozenset({"created", "eligible", "active", "stalled", "completed", "terminated", "pruned"})
ROUTE_COMMIT_TOKEN = object()
_ROUTE_IMMUTABLE_FIELDS = (
    "route_id", "parent_route_id", "kind", "frontier", "frontier_digest",
    "graph_version", "policy_version", "mutation", "created_revision",
    "plan_version", "attempt_index", "budget_at_start", "credit_at_start",
    "progress_at_start",
)
_ROUTE_REQUIRED_FIELDS = set(_ROUTE_IMMUTABLE_FIELDS) | {
    "status", "stop_reason", "elimination_reason", "verified_gain",
    "unknown_observations",
}
_ROUTE_OPTIONAL_FIELDS = {"needs_reevaluation"}


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
    if state.get("progress_policy") != {"enabled": True, "version": "progress-v1"}:
        return "route_progress_policy_required"
    method_error = route_plan_error(plan)
    if method_error is not None:
        return method_error
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
    if routes and route_budget.get("expansion_allowed") is False:
        return "route_expansion_budget_reserved"
    if state.get("budget", {}).get("exhaustion_reason"):
        return "route_expansion_budget_exhausted"
    if any(item.get("kind") == "alternate" for item in routes):
        return "alternate_route_limit_reached"
    return None


def route_plan_error(plan: Any) -> str | None:
    """Require the frozen S04 controlled method on every executable route step."""
    if not isinstance(plan, dict) or not isinstance(plan.get("steps"), list) or not plan["steps"]:
        return "empty_route_plan"
    from .progress import METHOD_IDS

    for step in plan["steps"]:
        if not isinstance(step, dict):
            return "route_method_required"
        method = step.get("method_id")
        if not isinstance(method, str) or method not in METHOD_IDS or method == "unknown":
            return "route_method_required"
    return None


def validate_route_state_patch(
    previous: dict[str, Any],
    event: dict[str, Any],
    updates: dict[str, Any],
    *,
    authorized: bool = False,
) -> None:
    """Validate all route-derived fields inside the SolverStateStore CAS transaction."""
    route_fields = {
        "route_registry", "route_lineage", "route_evaluations", "aprs_decisions",
        "route_invalidations", "active_route_id", "route_budget",
    }
    if route_fields.intersection(updates) and not authorized:
        raise ValueError("route_state_requires_internal_commit")
    if "route_policy" in updates:
        raise ValueError("route_policy_is_run_frozen")
    new_routes = updates.get("route_registry")
    if new_routes is not None:
        _validate_route_registry(previous, new_routes)
    old_lineage = previous.get("route_lineage", [])
    new_lineage = updates.get("route_lineage", old_lineage)
    if not isinstance(new_lineage, list) or new_lineage[:len(old_lineage)] != old_lineage:
        raise ValueError("route_lineage_rewrite")
    if new_routes is not None and len(new_lineage) == len(old_lineage):
        raise ValueError("route_lineage_missing_transition")
    _validate_route_projection(previous, updates)


def _validate_route_registry(previous: dict[str, Any], new_routes: Any) -> None:
    old_routes = previous.get("route_registry", [])
    if not isinstance(old_routes, list) or not isinstance(new_routes, list):
        raise ValueError("route_registry_invalid")
    old_ids = [item.get("route_id") for item in old_routes if isinstance(item, dict)]
    new_ids = [item.get("route_id") for item in new_routes if isinstance(item, dict)]
    if len(old_ids) != len(old_routes) or len(new_ids) != len(new_routes):
        raise ValueError("route_registry_invalid")
    if new_ids[:len(old_ids)] != old_ids or len(new_ids) > len(old_ids) + 1:
        raise ValueError("route_history_rewrite")
    for old, new in zip(old_routes, new_routes):
        if any(new.get(field) != old.get(field) for field in _ROUTE_IMMUTABLE_FIELDS):
            raise ValueError("route_identity_rewrite")
        if set(new) - _ROUTE_REQUIRED_FIELDS - _ROUTE_OPTIONAL_FIELDS:
            raise ValueError("route_fields_invalid")
        if new.get("status") not in ROUTE_STATES:
            raise ValueError("route_status_invalid")
    if len(new_routes) == len(old_routes) + 1:
        added = new_routes[-1]
        if (set(added) - _ROUTE_REQUIRED_FIELDS - _ROUTE_OPTIONAL_FIELDS
                or not _ROUTE_REQUIRED_FIELDS.issubset(added)):
            raise ValueError("route_creation_shape_invalid")
        if added.get("kind") not in {"primary", "alternate"}:
            raise ValueError("route_kind_invalid")
        if frontier_digest(added.get("frontier")) != added.get("frontier_digest"):
            raise ValueError("route_frontier_digest_invalid")
        if added.get("kind") == "primary" and old_routes:
            raise ValueError("primary_route_already_exists")
        if added.get("kind") == "alternate":
            primary = next((item for item in old_routes if item.get("kind") == "primary"), None)
            if primary is None or primary.get("status") != "stalled":
                raise ValueError("alternate_requires_stalled_primary")
            if any(item.get("kind") == "alternate" for item in old_routes):
                raise ValueError("alternate_route_limit_reached")


def _validate_route_projection(previous: dict[str, Any], updates: dict[str, Any]) -> None:
    routes = updates.get("route_registry", previous.get("route_registry", []))
    route_ids = {item.get("route_id") for item in routes if isinstance(item, dict)}
    active = updates.get("active_route_id", previous.get("active_route_id"))
    if active is not None and active not in route_ids:
        raise ValueError("active_route_not_found")
    if active is not None:
        route = next(item for item in routes if item.get("route_id") == active)
        if route.get("status") not in {"created", "eligible", "active", "stalled"}:
            raise ValueError("active_route_terminal")
    for field in ("route_evaluations", "aprs_decisions", "route_invalidations"):
        if field not in updates:
            continue
        old = previous.get(field, [])
        new = updates[field]
        if not isinstance(old, list) or not isinstance(new, list) or new[:len(old)] != old:
            raise ValueError(f"{field}_rewrite")
    if "route_evaluations" in updates:
        for record in updates["route_evaluations"][len(previous.get("route_evaluations", [])):]:
            if not isinstance(record, dict) or not isinstance(record.get("evaluations"), list):
                raise ValueError("route_evaluation_invalid")
            if any(item.get("route_id") not in route_ids for item in record["evaluations"] if isinstance(item, dict)):
                raise ValueError("route_evaluation_route_unknown")
    if "aprs_decisions" in updates:
        for decision in updates["aprs_decisions"][len(previous.get("aprs_decisions", [])):]:
            if not isinstance(decision, dict) or decision.get("policy_version") is None:
                raise ValueError("aprs_decision_invalid")
            selected = decision.get("selected_route_id")
            if selected is not None and selected not in route_ids:
                raise ValueError("aprs_selected_route_unknown")
            if any(route_id not in route_ids for route_id in decision.get("pareto_route_ids", [])):
                raise ValueError("aprs_pareto_route_unknown")
    if "route_invalidations" in updates:
        for item in updates["route_invalidations"][len(previous.get("route_invalidations", [])):]:
            if not isinstance(item, dict) or any(route_id not in route_ids for route_id in item.get("route_ids", [])):
                raise ValueError("route_invalidation_invalid")


def plan_frontier(plan: Any, specification: Any = None) -> list[dict[str, Any]]:
    if not isinstance(plan, dict):
        return []
    if not isinstance(specification, dict):
        return []
    objectives = {
        item.get("obligation_id"): {"kind": "root", **item}
        for item in specification.get("root_obligations", [])
        if isinstance(item, dict) and isinstance(item.get("obligation_id"), str)
    }
    objectives.update({
        item.get("goal_id"): {"kind": "auxiliary", **item}
        for item in specification.get("auxiliary_goals", [])
        if isinstance(item, dict) and isinstance(item.get("goal_id"), str)
    })
    targets = set()
    for step in plan.get("steps", []):
        if not isinstance(step, dict):
            continue
        method_id = normalize_method(step.get("method_id"))
        for objective_id in [*step.get("obligation_ids", []), *step.get("auxiliary_goal_ids", [])]:
            if not isinstance(objective_id, str) or objective_id not in objectives:
                continue
            objective = objectives[objective_id]
            prerequisites = objective.get("prerequisite_ids", objective.get("dependencies", []))
            targets.add(_canonical({
                "objective_id": objective_id,
                "kind": objective["kind"],
                "objective_type": objective.get("obligation_type"),
                "prerequisite_ids": sorted(item for item in prerequisites if isinstance(item, str)),
                "method_id": method_id,
            }))
    return [json.loads(item) for item in sorted(targets)]


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
    plan_version: int | None = None,
    attempt_index: int | None = None,
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
        "plan_version": plan_version,
        "attempt_index": attempt_index,
        "budget_at_start": deepcopy(
            state.get("route_budget", {}).get("current_snapshot")
        ),
        "credit_at_start": [],
        "progress_at_start": {
            "no_evidence_rounds": state.get("progress", {}).get("no_evidence_rounds", 0),
            "action_failures": deepcopy(state.get("progress", {}).get("action_failures", {})),
        },
        "verified_gain": [],
        "unknown_observations": [],
    }
    from .aprs import verified_gain

    route["credit_at_start"] = verified_gain(state)
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
    plan = state.get("plan")
    if not isinstance(plan, dict):
        return run
    frontier = plan_frontier(plan, state.get("problem_spec"))
    digest = frontier_digest(frontier)
    routes = state.get("route_registry") or []
    if any(
        item.get("frontier_digest") == digest
        and item.get("plan_version") == state.get("plan_version")
        and item.get("attempt_index") == state.get("attempt_index")
        for item in routes
    ):
        return run
    error = validate_route_frontier(state, plan)
    if error is not None:
        return harness.commit_event(
            run["run_id"], expected_revision=run["state_revision"],
            event={"event_id": f"route-precondition-failed-{run['state_revision']}",
                   "type": "route_precondition_failed", "route_reason": error,
                   "policy_version": state.get("route_policy", {}).get("policy_version")},
            state_updates={"phase": "TERMINAL", "status": "partial_aborted",
                           "result_reason": f"route_{error}",
                           "final_response": f"No verified final answer is available: route_{error}."},
        )
    kind = "primary" if not routes else "alternate"
    parent = None
    route_state = state
    if routes:
        active = next((item for item in routes if item.get("route_id") == state.get("active_route_id")), None)
        if active is None:
            return run
        if active.get("status") == "stalled":
            route_state = state
        else:
            route_state = {**state, **transition_route(state, active["route_id"], "stalled", reason="plan_replaced")}
        parent = active["route_id"]
    try:
        patch = register_route(route_state, frontier=frontier,
                               graph_version=(state.get("proof_graph") or {}).get("current_version"),
                               parent_route_id=parent, kind=kind,
                               mutation={"kind": "plan_replaced"} if parent else None,
                               state_revision=run["state_revision"] + 1,
                               plan_version=state.get("plan_version"),
                               attempt_index=state.get("attempt_index"))
    except ValueError:
        return run
    route = patch["route_registry"][-1]
    route["status"] = "active"
    patch["route_lineage"].append({"event": "route_transition", "route_id": route["route_id"],
                                    "status": "active", "reason": "route_selected"})
    return harness._commit_route_event(
        run["run_id"], expected_revision=run["state_revision"],
        event={"event_id": f"route-created-{run['state_revision']}-{route['route_id']}",
               "type": "route_created", "route_id": route["route_id"],
               "parent_route_id": parent, "route_kind": kind,
               "frontier_digest": digest, "route_status": "active",
               "policy_version": route["policy_version"], "route_reason": "plan_boundary",
               "route_count": len(patch["route_registry"])},
        state_updates=patch,
        authorization=ROUTE_COMMIT_TOKEN,
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
    return harness._commit_route_event(
        run["run_id"], expected_revision=run["state_revision"],
        event={"event_id": f"route-stalled-{run['state_revision']}", "type": "route_transition",
               "route_id": active["route_id"], "route_status": "stalled",
               "route_reason": "s04_stagnation",
               "policy_version": state["route_policy"]["policy_version"]},
        state_updates=patch,
        authorization=ROUTE_COMMIT_TOKEN,
    )
