"""Record bounded, non-authoritative observations from completed STAR Runs."""

from __future__ import annotations

import sqlite3
from collections import Counter
from collections.abc import Mapping

from .faithful_memory import FaithfulMemoryStore, MemoryScope

_ROUTE_REASONS = frozenset({
    "run_aborted", "budget_exhausted", "run_completed_unverified", "run_failed",
    "run_canceled", "run_interrupted", "run_terminal_unverified", "final_answer_bound",
    "plan_replaced", "s04_stagnation", "stagnation", "local_action_blocked",
})


def capture_population_observation(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    state: Mapping,
    budget: Mapping | None,
    reviewed: bool,
) -> bool:
    """Persist one idempotent observation only after explicit session opt-in."""
    if connection.in_transaction:
        return False
    specification = state.get("problem_spec")
    domain = specification.get("domain") if isinstance(specification, Mapping) else None
    if state.get("phase") != "TERMINAL" or not isinstance(domain, str) or not domain.strip():
        return False

    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS faithful_memory_observation_sources ("
            "run_id TEXT PRIMARY KEY, record_id TEXT NOT NULL)"
        )
        connection.execute("BEGIN IMMEDIATE")
        job = connection.execute(
            "SELECT j.user_id,j.session_id,s.user_id FROM workspace_jobs j "
            "JOIN chat_sessions s ON s.session_id=j.session_id WHERE j.job_id=?",
            (run_id,),
        ).fetchone()
        if job is None or job[0] != job[2]:
            connection.rollback()
            return False
        owner_id, session_id = job[0], job[1]
        control = connection.execute(
            "SELECT enabled FROM faithful_memory_injection_controls "
            "WHERE owner_id=? AND workspace_id=? AND scope_kind='population' AND scope_id=?",
            (owner_id, session_id, session_id),
        ).fetchone()
        if control is None or not bool(control[0]):
            connection.rollback()
            return False
        existing = connection.execute(
            "SELECT record_id FROM faithful_memory_observation_sources WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if existing is not None:
            connection.rollback()
            return False

        status = state.get("status")
        calls = state.get("calls", {})
        unknown_budget = (
            isinstance(budget, Mapping)
            and int(budget.get("unknown_attempts", 0) or 0) > 0
        )
        unknown_calls = isinstance(calls, Mapping) and any(
            isinstance(call, Mapping) and call.get("status") == "unknown_outcome"
            for call in calls.values()
        )
        unknown = unknown_budget or unknown_calls
        outcome = "unknown" if unknown else "success" if reviewed is True else "failure"
        routes = state.get("route_registry", [])
        route_entries = routes if isinstance(routes, list) else []
        delivered_routes = {
            route.get("route_id")
            for route in route_entries if isinstance(route, Mapping)
            and route.get("status") == "completed"
            and route.get("stop_reason") == "final_answer_bound"
            and isinstance(route.get("route_id"), str)
        }
        delivered_route_id = next(iter(delivered_routes)) if reviewed is True and len(delivered_routes) == 1 else None
        route_statuses = Counter(
            str(route.get("status"))
            for route in route_entries
            if isinstance(route, Mapping) and isinstance(route.get("status"), str)
        )
        limits = budget if isinstance(budget, Mapping) else {}
        scope = MemoryScope("population", session_id, owner_id, session_id)
        store = FaithfulMemoryStore(connection)
        record_id = store.record_observation(
            scope,
            {
                "outcome": outcome,
                "applicability": {"domain": domain.strip()},
                "versions": {
                    key: value
                    for key, value in {
                        "plan_version": state.get("plan_version"),
                        "graph_version": (state.get("proof_graph") or {}).get("current_version")
                        if isinstance(state.get("proof_graph"), Mapping) else None,
                        "policy_version": (state.get("route_policy") or {}).get("policy_version")
                        if isinstance(state.get("route_policy"), Mapping) else None,
                    }.items()
                    if value is not None
                },
                "cost": {
                    key: limits[key]
                    for key in (
                        "logical_calls", "http_attempts", "tool_calls", "charged_tokens",
                        "unknown_attempts", "wall_time_seconds",
                    )
                    if key in limits
                },
                "content": {
                    "run_status": status if isinstance(status, str) else "unknown",
                    "route_status_counts": dict(sorted(route_statuses.items())),
                },
            },
            provenance={"source_run_id": run_id, "source_state_revision": state.get("state_revision", 0)},
        )
        for route in route_entries:
            observation = _route_observation(
                route, domain.strip(), unknown, reviewed,
                delivery_route_id=delivered_route_id, cost=_route_cost(state, route),
            )
            if observation is not None:
                store.record_observation(
                    scope, observation,
                    provenance={"source_run_id": run_id,
                                "source_state_revision": state.get("state_revision", 0)},
                )
        connection.execute(
            "INSERT INTO faithful_memory_observation_sources(run_id,record_id) VALUES (?,?)",
            (run_id, record_id),
        )
        connection.commit()
        return True
    except (sqlite3.Error, ValueError):
        if connection.in_transaction:
            connection.rollback()
        return False


def _route_observation(route, domain, run_unknown, reviewed, *, delivery_route_id=None, cost=None):
    """Describe a route without attributing the Run's resources or proof to it."""
    if not isinstance(route, Mapping):
        return None
    route_id, digest = route.get("route_id"), route.get("frontier_digest")
    if not all(isinstance(value, str) and value for value in (route_id, digest)):
        return None
    status = route.get("status")
    if run_unknown or route.get("unknown_observations"):
        outcome = "unknown"
    elif status == "completed" and reviewed is True and route_id == delivery_route_id:
        outcome = "success"
    elif status in {"terminated", "pruned"}:
        outcome = "failure"
    else:
        outcome = "unknown"
    return {
        "outcome": outcome,
        "applicability": {"domain": domain},
        "versions": {key: route[key] for key in
                     ("graph_version", "plan_version", "attempt_index", "policy_version")
                     if route.get(key) is not None},
        "cost": cost if isinstance(cost, Mapping) else {"status": "unknown"},
        "content": {
            "route_id": route_id, "frontier_digest": digest, "route_status": status,
            **{key: route[key] if route[key] in _ROUTE_REASONS else "other"
               for key in ("stop_reason", "elimination_reason")
               if isinstance(route.get(key), str) and route[key]},
        },
    }


def _route_cost(state, route):
    """Read the first terminal APRS snapshot, never the Run-wide budget total."""
    route_id, status = route.get("route_id"), route.get("status")
    if not isinstance(route_id, str) or status not in {"stalled", "completed", "terminated", "pruned"}:
        return {"status": "unknown"}
    for group in state.get("route_evaluations", []):
        for evaluation in group.get("evaluations", []):
            snapshot = evaluation.get("snapshot")
            if (not isinstance(snapshot, Mapping) or snapshot.get("route_id") != route_id
                    or snapshot.get("route_status") != status):
                continue
            if snapshot.get("cost_known") is not True:
                return {"status": "unknown"}
            resources = snapshot.get("consumed_resources")
            if not isinstance(resources, Mapping):
                return {"status": "unknown"}
            return {
                "status": "measured",
                "basis": snapshot.get("cost_basis", "route_delta"),
                **{
                    key: resources[key]
                    for key in ("charged_tokens", "logical_calls", "http_attempts", "tool_calls",
                                "tool_wall_time_seconds", "wall_time_seconds")
                    if key in resources and resources[key] is not None
                },
            }
    return {"status": "unknown"}
