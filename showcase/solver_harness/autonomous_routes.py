"""Initial route selection within a frozen permission and the existing root ledger."""

import time
from copy import deepcopy


def freeze_permission(config, population_config, unavailable_reason):
    """Freeze optional concurrency before creating the ordinary Run identity."""
    if config.get("features", {}).get("auto_problem_spec") is not True:
        return
    policy = deepcopy((population_config or {}).get("population_policy"))
    if policy is None:
        return  # Preserve the config identity of pre-Population ordinary tasks.
    config["autonomous_routes"] = {
        "version": "autonomous-routes-v1", "population_policy": policy,
        "unavailable_reason": unavailable_reason if policy is None else None,
    }
    if policy:
        # RouteHarness reads the frozen action limits without replacing config/hash.
        policy["max_challenge_rounds"] = 1
        config["population_policy"] = policy


def initial_permission(config, unavailable_reason=None):
    """Only new ordinary tasks receive a selection contract; old tasks stay unchanged."""
    return deepcopy(config.get("autonomous_routes") or {
        "version": "autonomous-routes-v1", "population_policy": None,
        "unavailable_reason": unavailable_reason or "population_not_enabled",
    })


def planner_request(harness, run, request):
    """Ask the model to choose initial execution using goals and actual resources."""
    permission = run["state"].get("autonomous_routes")
    if not permission or run["state"].get("execution_selection"):
        return request
    from .route_budget import route_budget_snapshot

    budget = route_budget_snapshot(harness._state_store._connection, run["run_id"])
    policy = permission.get("population_policy") or {}
    return {**request, "autonomous_routes": {
        "version": permission["version"], "capacity": policy.get("capacity"),
        "unavailable_reason": permission.get("unavailable_reason"), "root_budget": budget,
    }, "instruction": request.get("instruction", "") + (
        " Choose execution_selection {mode: serial|population, reason: a short public summary}. "
        "Use goals, independent directions, available capacity and remaining root budget. "
        "For population, propose alternative_plans with distinct controlled methods/frontiers, "
        "each covering all root obligations. Renaming steps is not independence. "
        "Choose serial when independent exploration adds no value. This selects initial execution; "
        "mid-run switching is unavailable. Never invent capacity or increase the root budget."
    )}


def select_initial_execution(harness, run, problem):
    """Admit a model proposal before any WorkUnit, or persist a legal serial reason."""
    state = run["state"]
    permission = state.get("autonomous_routes")
    if (not permission or state.get("execution_selection") or state["phase"] != "STEP_EXECUTE"
            or state.get("replan_count", 0) or state.get("steps")
            or state.get("route_registry")):
        return run
    from ..redaction import redact
    from .population_runtime import _estimates, register_plans
    from .route_budget import route_budget_snapshot

    plan = state["plan"]
    proposal = plan.get("execution_selection") or {}
    policy = permission.get("population_policy") or {}
    capacity = policy.get("capacity") or {}
    plans = _independent_plans(plan, state["problem_spec"])
    snapshot = route_budget_snapshot(harness._state_store._connection, run["run_id"])
    reason = (permission.get("unavailable_reason")
              or ("model_selected_serial" if proposal else "no_population_proposal"))
    selected = "serial"
    reserves = []
    closing = {}
    if proposal.get("mode") == "population":
        if not policy:
            reason = permission.get("unavailable_reason") or "population_not_enabled"
        elif min(capacity["max_inflight"], capacity["worker_slots"]) < 2:
            reason = "parallel_capacity_unavailable"
        elif len(plans) < 2:
            reason = "independent_frontiers_required"
        else:
            try:
                for candidate in plans[:capacity["max_inflight"]]:
                    local = {**state, "plan": candidate, "population_policy": policy,
                             "current_step": candidate["steps"][0]["step_id"]}
                    reserve, closing = _estimates(
                        harness, {**run, "state": local}, {"snapshot": local}, problem)
                    reserves.append(reserve)
                limits = snapshot["limits"]
                enough = all(
                    limits[limit] - snapshot[used] >= closing[field]
                    + sum(item[field] for item in reserves)
                    for field, limit, used in (
                        ("model_calls", "max_model_calls", "logical_calls"),
                        ("http_attempts", "max_http_attempts", "http_attempts"),
                        ("tokens", "max_tokens", "charged_tokens")))
                enough = enough and snapshot["deadline_at"] - time.time() >= (
                    closing["time_seconds"] + max(item["time_seconds"] for item in reserves))
                selected, reason = (("population", "independent_routes_admitted") if enough
                                    else ("serial", "root_budget_insufficient"))
            except (TypeError, ValueError) as exc:
                reason = str(exc)
    selection = {
        "version": permission["version"], "requested": proposal.get("mode", "serial"),
        "selected": selected, "reason": reason,
        "proposal_reason": redact(str(proposal.get("reason", ""))[:400]),
        "independent_routes": len(plans),
        "capacity": {key: capacity.get(key) for key in ("max_inflight", "worker_slots")},
        "budget": {"limits": snapshot.get("limits"), "deadline_at": snapshot.get("deadline_at"),
                   "logical_calls": snapshot.get("logical_calls"),
                   "http_attempts": snapshot.get("http_attempts"),
                   "closing_reserve": closing, "route_reservations": reserves},
    }
    updates = {"execution_selection": selection}
    if selected == "population":
        from .population_store import initial_population

        updates.update(population_policy=deepcopy(policy), population=initial_population())
    run = harness.commit_event(run["run_id"], expected_revision=run["state_revision"],
        event={"event_id": "initial-execution-selected", "type": "execution_selected",
               "selected": selected, "reason": reason}, state_updates=updates)
    if selected == "population":
        from .population_lifecycle import claim

        run = claim(harness, run)
        # Only validated distinct proposals enter the existing executor.
        run = register_plans(harness, run, {**plans[0], "alternative_plans": plans[1:]})
    return run


def _independent_plans(plan, specification):
    from .plan import validate_plan
    from .routes import frontier_digest, plan_frontier, route_plan_error
    from .specification import bind_plan_work_units

    plans, digests = [], set()
    for proposal in [plan, *plan.get("alternative_plans", [])]:
        try:
            validate_plan(proposal)
            if route_plan_error(proposal):
                continue
            bound, _ = bind_plan_work_units(proposal, specification)
            digest = frontier_digest(plan_frontier(bound, specification))
            if digest not in digests:
                digests.add(digest)
                plans.append(bound)
        except (TypeError, ValueError):
            continue
    return plans
