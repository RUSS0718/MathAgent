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
        "Place execution_selection only on the primary top-level plan, alongside checkpoint in checkpoint replies. "
        "NEVER include execution_selection in alternative_plans; alternatives must be "
        "normal complete plans without execution_selection. "
        "Use goals, independent directions, available capacity and remaining root budget. "
        "For population, the primary plan must itself be one complete whole-problem route, "
        "not a union or coordinator of methods. Put other complete independent routes only in "
        "alternative_plans, not in the primary steps. "
        "Do not schedule cross-route reconciliation or waiting as primary work; "
        "the executor manages the route race and first qualified delivery. "
        "For population, propose alternative_plans with distinct controlled methods/frontiers, "
        "each covering all root obligations. Renaming steps is not independence. "
        "When any one complete proof suffices for delivery, treat optional whole-proof directions as "
        "alternative complete plans, not mandatory proof steps after a shared answer. "
        "Each route must establish its own conclusions, equality conditions and completeness as applicable; "
        "do not depend on another route's unverified result. "
        "Explore candidates are unverified: check elementary substitutions and "
        "never freeze their maximum or equality claims as established. "
        "Choose one complete serial method when independent exploration adds no value "
        "or its budget cost is not justified, and explain why. This selects initial execution; "
        "mid-run execution follows verified progress under the same permission. Never invent capacity or increase the root budget."
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
    from .population_runtime import prepare_population_plan

    plans, digests = [], set()
    for proposal in [plan, *plan.get("alternative_plans", [])]:
        try:
            bound, digest = prepare_population_plan(proposal, specification)
            if digest not in digests:
                digests.add(digest)
                plans.append(bound)
        except (TypeError, ValueError):
            continue
    return plans


def current_mode(state):
    return (state.get("execution_switch") or {}).get("current_mode", (
        state.get("execution_selection") or {}).get("selected", "serial"))


def advance_switch(harness, run, problem):
    """Persist intent before dispatch; converge receipts through the existing executor."""
    from .obligation_evidence import all_root_obligations_satisfied
    from .population_runtime import _collect
    from .population_store import command, initial_population

    state = run["state"]
    permission = state.get("autonomous_routes") or {}
    if not permission.get("population_policy") or not state.get("execution_selection"):
        return run
    switch = state.get("execution_switch") or {}
    if switch.get("status") in {"converging", "needs_review"}:
        if state.get("population"):
            futures = list(harness._population_futures.values())
            if futures:
                from concurrent.futures import wait, FIRST_COMPLETED

                wait(futures, timeout=30, return_when=FIRST_COMPLETED)
            run = _collect(harness, run)
        if switch["source"] == "serial":
            run = _seed_serial(harness, run)
        return command(harness, run["run_id"], "execution_checkpoint",
                       expected_revision=run["state_revision"])
    if state.get("phase") not in {"STEP_EXECUTE", "POPULATION", "META_DECIDE"}:
        return run
    if all_root_obligations_satisfied(state.get("obligation_ledger", [])):
        return run
    mode = current_mode(state)
    # Expansion is bounded to the original Planner's independently validated plans.
    # A later serial checkpoint remains stable for interventions, without oscillation.
    if mode == "serial":
        if switch or not state.get("steps") or state.get("phase") != "STEP_EXECUTE":
            return run
        plans = _independent_plans(state["plan"], state["problem_spec"])
        if len(plans) < 2 or not _switch_budget_available(harness, run, plans, problem):
            return run
        if not any(item.get("verification", {}).get("valid") is True
                   and item["verification"].get("verdict") == "ACCEPT"
                   for item in state["steps"].values()):
            return run
        reason, target = "reviewed_serial_progress_with_independent_frontiers", "population"
    else:
        actions = state.get("population", {}).get("actions", {}).values()
        if not any(a.get("accepted") and a.get("acceptance_reason") is None for a in actions):
            return run
        reason, target = "population_progress_converge_to_ranked_route", "serial"
    projection = {"status": "converging", "source": mode, "target": target,
                  "reason": reason, "checkpoint_revision": None, "current_mode": mode}
    updates = {"execution_switch": projection}
    if mode == "serial":
        from .population_store import _canonical
        import hashlib

        updates.update(population=initial_population(),
                       population_policy=deepcopy(permission["population_policy"]),
                       execution_serial_sources={key: hashlib.sha256(_canonical(call).encode()).hexdigest()
                           for key, call in state.get("calls", {}).items()
                           if call.get("status") == "completed"})
    if mode == "population":
        run = command(harness, run["run_id"], "execution_intent", projection=projection)
    else:
        run = harness.commit_event(run["run_id"], expected_revision=run["state_revision"],
            event={"event_id": f"execution-switch-intent-{run['state_revision']}",
                   "type": "execution_switch_intent", **projection}, state_updates=updates)
    if mode == "serial":
        from .population_lifecycle import claim

        run = claim(harness, run)
        run = _seed_serial(harness, run)
    return command(harness, run["run_id"], "execution_checkpoint",
                   expected_revision=run["state_revision"])


def _seed_serial(harness, run):
    """Keep the completed serial work and identities as the primary route snapshot."""
    from .population_runtime import prepare_population_plan, register_plans
    from .population_store import command

    state = run["state"]
    _, digest = prepare_population_plan(state["plan"], state["problem_spec"])
    rid = "route-" + digest[:20]
    if rid not in state["population"]["routes"]:
        snapshot = {k: deepcopy(v) for k, v in state.items()
                    if k not in {"population", "population_policy", "execution_switch"}}
        run = command(harness, run["run_id"], "register_route", route_id=rid,
                      frontier_digest=digest, snapshot=snapshot, dependencies=[])
    return register_plans(harness, run, state["plan"])


def cancel_switch(connection, run_id, now):
    """Cancel a pending switch in the Job cancellation transaction."""
    import json
    from .storage import _json

    if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='solver_states'").fetchone():
        return
    row = connection.execute("SELECT state_json,state_revision FROM solver_states WHERE run_id=?",
                             (run_id,)).fetchone()
    if row is None:
        return
    state = json.loads(row["state_json"])
    switch = state.get("execution_switch") or {}
    if switch.get("status") not in {"converging", "needs_review"}:
        return
    revision = row["state_revision"] + 1
    state.update(execution_switch={**switch, "status": "canceled", "checkpoint_revision": None},
                 serial_checkpoint=None, state_revision=revision, updated_at=now)
    connection.execute("UPDATE solver_states SET state_json=?,state_revision=?,updated_at=? WHERE run_id=?",
                       (_json(state), revision, now, run_id))
    sequence = connection.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM solver_events WHERE run_id=?",
                                  (run_id,)).fetchone()[0]
    event = {"event_id": f"execution-switch-canceled-{revision}", "type": "execution_switch_canceled",
             "run_id": run_id, "state_revision": revision, "created_at": now}
    connection.execute("INSERT INTO solver_events(run_id,sequence,event_id,state_revision,event_json,created_at) VALUES(?,?,?,?,?,?)",
                       (run_id, sequence, event["event_id"], revision, _json(event), now))


def _switch_budget_available(harness, run, plans, problem):
    from .population_runtime import _estimates
    from .route_budget import route_budget_snapshot

    policy = run["state"]["autonomous_routes"]["population_policy"]
    budget = route_budget_snapshot(harness._state_store._connection, run["run_id"])
    reserves = []
    try:
        for index, plan in enumerate(plans[:policy["capacity"]["max_inflight"]]):
            local = {**run["state"], "population_policy": policy}
            if index:
                local.update(plan=plan, current_step=plan["steps"][0]["step_id"])
            reserve, closing = _estimates(harness, {**run, "state": local},
                                          {"snapshot": local}, problem)
            reserves.append(reserve)
        return all(budget["limits"][limit] - budget[used] >= closing[field]
                   + sum(item[field] for item in reserves)
                   for field, limit, used in (
                       ("model_calls", "max_model_calls", "logical_calls"),
                       ("http_attempts", "max_http_attempts", "http_attempts"),
                       ("tokens", "max_tokens", "charged_tokens"))) and (
            budget["deadline_at"] - time.time() >= closing["time_seconds"]
            + max(item["time_seconds"] for item in reserves))
    except (TypeError, ValueError):
        return False
