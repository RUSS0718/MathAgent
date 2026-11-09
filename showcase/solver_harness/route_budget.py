"""Read-only serial-route expansion estimates over the shared Run ledger."""

from __future__ import annotations

import math
import time


def derive_route_budget(connection, run_id, base=None, *, now=None):
    """Refresh remaining resources while preserving the latest read-only reserve."""
    from ..run_budget import _summary

    try:
        row = connection.execute(
            "SELECT ledger_json FROM run_budgets WHERE run_id = ?", (run_id,)
        ).fetchone()
    except Exception:
        row = None
    if row is None:
        return {
            "source": "shared_run_budget",
            "available": False,
            "expansion_allowed": False,
            "stop_reason": "shared_budget_unavailable",
            "current_snapshot": None,
            "closing_reserve": {},
            "planner_reserve": {},
            "work_unit_reserve": {},
            "unknown": ["budget_snapshot"],
        }
    import json

    snapshot = _summary(json.loads(row[0]))
    limits = snapshot["limits"]
    remaining = {
        "model_calls": max(0, limits["max_model_calls"] - snapshot["logical_calls"]),
        "http_attempts": max(0, limits["max_http_attempts"] - snapshot["http_attempts"]),
        "tool_calls": max(0, limits["max_tool_calls"] - snapshot["tool_calls"]),
        "tokens": max(0, limits["max_tokens"] - snapshot["charged_tokens"]),
    }
    prior = base if isinstance(base, dict) else {}
    closing = prior.get("closing_reserve") or {}
    planner = prior.get("planner_reserve") or {}
    work_unit = prior.get("work_unit_reserve") or {}
    effective_deadline = prior.get("effective_deadline_at")
    clock = time.time() if now is None else now
    usable = prior.get("preflight_valid") is True
    for field in ("model_calls", "http_attempts", "tokens", "time_seconds"):
        usable = usable and type(closing.get(field)) in {int, float}
        usable = usable and type(planner.get(field)) in {int, float}
        usable = usable and type(work_unit.get(field)) in {int, float}
    if type(effective_deadline) not in {int, float} or not math.isfinite(effective_deadline):
        usable = False
    route_execution_allowed = usable and (
        remaining["model_calls"] >= closing["model_calls"] + work_unit["model_calls"]
        and remaining["http_attempts"] >= closing["http_attempts"] + work_unit["http_attempts"]
        and remaining["tokens"] >= closing["tokens"] + work_unit["tokens"]
        and effective_deadline - clock >= closing["time_seconds"] + work_unit["time_seconds"]
    )
    expansion_allowed = route_execution_allowed and (
        remaining["model_calls"] >= closing["model_calls"] + planner["model_calls"]
        + work_unit["model_calls"]
        and remaining["http_attempts"] >= closing["http_attempts"] + planner["http_attempts"]
        + work_unit["http_attempts"]
        and remaining["tokens"] >= closing["tokens"] + planner["tokens"] + work_unit["tokens"]
        and effective_deadline - clock >= closing["time_seconds"] + planner["time_seconds"]
        + work_unit["time_seconds"]
    )
    unknown = [
        field for field, count in snapshot.get("provider_unknown_fields", {}).items() if count
    ]
    return {
        "source": "shared_run_budget",
        "available": True,
        "expansion_allowed": bool(expansion_allowed),
        "route_execution_allowed": bool(route_execution_allowed),
        "stop_reason": None if expansion_allowed else (
            prior.get("stop_reason") or "closing_reserve_required"
        ),
        "preflight_valid": prior.get("preflight_valid") is True,
        "current_snapshot": snapshot,
        "remaining": remaining,
        "closing_reserve": closing,
        "planner_reserve": planner,
        "work_unit_reserve": work_unit,
        "effective_deadline_at": effective_deadline,
        "unknown": unknown,
    }


def expansion_budget(harness, run, problem, model_port, planner_request):
    """Estimate Planner plus existing S03 finalization reserve without reserving it."""
    from .finalize import (
        _serialized_request_size,
        finalization_requests,
        finalization_reserve_estimate,
        proof_basis,
        valid_facts,
    )

    state = run["state"]
    adapter = getattr(model_port, "adapter", None)
    output_cap = getattr(adapter, "max_tokens", None)
    client_getter = getattr(adapter, "_get_client", None)
    client = client_getter() if callable(client_getter) else None
    timeout = getattr(client, "timeout", None) or getattr(adapter, "client_timeout", None)
    retries = getattr(client, "retry", None)
    if type(output_cap) is not int or output_cap <= 0:
        return _unavailable("finalization_output_cap_unavailable")
    if type(timeout) not in {int, float} or not math.isfinite(timeout) or timeout <= 0:
        return _unavailable("closing_timeout_unavailable")
    if type(retries) is not int or retries < 0:
        return _unavailable("closing_retry_bound_unavailable")

    session = (
        f"final:{run['run_id']}:plan{state['plan_version']}:attempt{state['attempt_index']}"
        f":candidate{len(state.get('final_solution_attempts', []))}"
    )
    attempts_history = state.get("final_solution_attempts") or []
    previous_review = attempts_history[-1].get("review") if attempts_history else None
    generator, review = finalization_requests(
        problem, valid_facts(state), proof_basis(state), session,
        previous_review,
        False,
    )
    try:
        closing = finalization_reserve_estimate(
            harness, model_port, run, generator, review,
            require_cap=True, use_snapshot=True,
        )
        planner_tokens = (
            _serialized_request_size(harness, model_port, run, planner_request,
                                    use_snapshot=True)
            + 1_024 + output_cap
        )
    except Exception:
        return _unavailable("closing_reserve_estimate_unavailable")

    attempts = retries + 1
    if state.get("population_policy", {}).get("enabled") is True:
        attempts = state["population_policy"].get("retry_limit", 1)
    closing_reserve = {
        "model_calls": 2,
        "http_attempts": 2,
        "tokens": closing["tokens"],
        "time_seconds": 2 * timeout * attempts,
    }
    planner_reserve = {
        "model_calls": 1,
        "http_attempts": 1,
        "tokens": planner_tokens,
        "time_seconds": timeout * attempts,
    }
    work_unit_reserve = {
        "model_calls": 2,
        "http_attempts": 2,
        "tokens": 2 * (1_024 + output_cap),
        "time_seconds": 2 * timeout * attempts,
    }
    base_snapshot = route_budget_snapshot(harness._state_store._connection, run["run_id"])
    deadlines = getattr(model_port, "deadlines", None) or {}
    candidates = [base_snapshot.get("deadline_at")]
    for name in ("phase_deadline_at", "batch_deadline_at"):
        value = deadlines.get(name)
        if value is not None:
            if type(value) not in {int, float} or not math.isfinite(value):
                return _unavailable("scoped_deadline_invalid")
            candidates.append(value)
    if not candidates or any(type(value) not in {int, float} for value in candidates):
        return _unavailable("run_deadline_unavailable")
    deadline = min(candidates)
    base = {
        "source": "shared_run_budget",
        "preflight_valid": True,
        "closing_reserve": closing_reserve,
        "planner_reserve": planner_reserve,
        "work_unit_reserve": work_unit_reserve,
        "effective_deadline_at": deadline,
        "stop_reason": None,
    }
    return derive_route_budget(
        harness._state_store._connection, run["run_id"], base
    )


def route_budget_snapshot(connection, run_id):
    """Return the actual shared ledger snapshot for one registered Run."""
    import json

    from ..run_budget import _summary

    row = connection.execute(
        "SELECT ledger_json FROM run_budgets WHERE run_id = ?", (run_id,)
    ).fetchone()
    return _summary(json.loads(row[0])) if row is not None else {}


def _unavailable(reason):
    return {
        "source": "shared_run_budget",
        "available": False,
        "expansion_allowed": False,
        "preflight_valid": False,
        "stop_reason": reason,
        "current_snapshot": None,
        "closing_reserve": {},
        "planner_reserve": {},
        "work_unit_reserve": {},
        "unknown": [reason],
    }
