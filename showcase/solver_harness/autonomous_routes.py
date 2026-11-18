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
                from concurrent.futures import FIRST_COMPLETED, wait

                wait(futures, timeout=30, return_when=FIRST_COMPLETED)
            run = _collect(harness, run)
        if any(r.get("snapshot", {}).get("authorized_retry") for r in run["state"].get("population", {}).get("routes", {}).values()):
            from .population_runtime import tick

            return tick(harness, run, problem)
        if switch["source"] == "serial" and not state.get("execution_serial_route"):
            run = _seed_serial(harness, run)
        return command(harness, run["run_id"], "execution_checkpoint",
                       expected_revision=run["state_revision"])
    if state.get("phase") not in {"STEP_EXECUTE", "POPULATION", "META_DECIDE"}:
        return run
    if all_root_obligations_satisfied(state.get("obligation_ledger", [])):
        return run
    mode = current_mode(state)
    local = state
    serial_route = state.get("execution_serial_route")
    if serial_route:
        local = state["population"]["routes"][serial_route]["snapshot"]
    plans = _independent_plans(local["plan"], state["problem_spec"])
    if mode == "serial" and (len(plans) < 2 and not serial_route):
        return run
    if (state.get('population_intervention') or {}).get('status') == 'executing':
        return run
    # Receipts, rather than ticks or audit revisions, bound model deliberation.
    marker = {"rounds": state.get("progress", {}).get("rounds", 0),
              "actions": sorted(a["action_id"] for a in state.get("population", {}).get("actions", {}).values()
                                if a.get("accepted")),
              "steps": sorted(k for k, v in state.get("steps", {}).items() if v.get("verification")),
              "trigger": state.get("progress", {}).get("trigger")}
    if not (marker["rounds"] or marker["actions"] or marker["steps"] or marker["trigger"]):
        return run
    pending = state.get("execution_mode_pending")
    if pending:
        marker = pending["marker"]
    if not pending and state.get("execution_mode_progress") == marker:
        return run
    run, proposal = _mode_decision(harness, run, problem, mode, marker, local)
    state = run["state"]
    target = proposal.get("mode", "keep")
    if target == "intervene":
        if state.get('serial_intervention') or (state.get('population_intervention') or {}).get('status') == 'completed':
            run = harness.commit_event(run['run_id'], expected_revision=run['state_revision'],
                event={'event_id': f"population-intervention-rejected-{run['state_revision']}",
                       'type': 'population_intervention_rejected', 'reason': 'population_intervention_already_used'},
                state_updates={})
            state = run['state']
            target = 'keep'
        elif (mode != "population" or not getattr(harness, "_intervention_enabled", False)
                or state.get("serial_intervention_permission") != {"enabled": True, "version": "serial-intervention-v1"}):
            target = "keep"
        else:
            from ..run_control import check_control
            from .storage import SolverRevisionConflictError

            while True:
                check_control()
                run = harness.get_run(run["run_id"])
                try:
                    run = harness.commit_event(run["run_id"], expected_revision=run["state_revision"],
                        event={"event_id": f"population-intervention-intent-{run['state_revision']}",
                               "type": "population_intervention_intent"},
                        state_updates={"population_intervention": {"status": "converging"}})
                    break
                except SolverRevisionConflictError:
                    continue
            state = run["state"]
            target = "serial"
    if target in {"keep", mode} or (target == "population" and not _switch_budget_available(harness, run, plans, problem)):
        from .storage import SolverRevisionConflictError

        while True:
            run = harness.get_run(run["run_id"])
            try:
                return harness.commit_event(run["run_id"], expected_revision=run["state_revision"],
                    event={"event_id": f"execution-mode-consumed-{run['state_revision']}", "type": "execution_mode_consumed"},
                    state_updates={"execution_mode_progress": marker, "execution_mode_pending": None})
            except SolverRevisionConflictError:
                continue
    reason = ("reviewed_serial_progress_with_independent_frontiers" if target == "population"
              else "population_progress_converge_to_ranked_route")
    projection = {"status": "converging", "source": mode, "target": target,
                  "reason": reason, "checkpoint_revision": None, "current_mode": mode}
    updates = {"execution_switch": projection, "execution_mode_progress": marker,
               "execution_mode_pending": None}
    if mode == "serial" and not state.get("population"):
        import hashlib

        from .population_store import _canonical

        updates.update(population=initial_population(),
                       population_policy=deepcopy(permission["population_policy"]),
                       execution_serial_sources={key: hashlib.sha256(_canonical(call).encode()).hexdigest()
                           for key, call in state.get("calls", {}).items()
                           if call.get("status") == "completed"})
    if state.get("population"):
        run = command(harness, run["run_id"], "execution_intent", projection=projection, mode_progress=marker)
    else:
        run = harness.commit_event(run["run_id"], expected_revision=run["state_revision"],
            event={"event_id": f"execution-switch-intent-{run['state_revision']}",
                   "type": "execution_switch_intent", **projection}, state_updates=updates)
    if mode == "serial" and not serial_route:
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
        if snapshot.get("phase") == "META_DECIDE":
            snapshot["phase"] = "STEP_EXECUTE"
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


def _mode_decision(harness, run, problem, mode, marker, local):
    from ..redaction import redact
    from .budget import budget_reason
    from .route_budget import route_budget_snapshot

    if not run["state"].get("execution_mode_pending") and (harness._meta_port is None or budget_reason(run["state"], harness._config)):
        return run, {"mode": "keep"}
    run = harness.get_run(run["run_id"])
    revision = run["state_revision"]
    request = {"role": "meta", "run_id": run["run_id"], "problem": problem,
               "session_key": f"execution-mode:{run['run_id']}",
               "call_id": f"execution-mode:{revision}", "execution_mode_decision": True,
               "current_mode": mode, "progress": deepcopy(local.get("progress", {})),
               "frontiers": [{"route_id": r["route_id"], "status": r["status"],
                              "progress": r["snapshot"].get("progress", {})}
                             for r in run["state"].get("population", {}).get("routes", {}).values()],
               "plan": deepcopy(local.get("plan")),
               "root_budget": route_budget_snapshot(harness._state_store._connection, run["run_id"]),
               "instruction": "Choose mode serial, population, or keep from current progress, stagnation, unfinished goals and independent fronts. Keep useful parallel work; expand stalled serial work only when independent fronts justify cost. Choose intervene only for a falsifiable mathematical obstacle requiring a controlled method experiment; this first converges all routes to a legal serial checkpoint, then asks the intervention decision. Never use it for transport failure.",
               "allowed_tools": [], "tool_policy": {"allow": []}}
    from .calls import CallInterrupted, latest_retry_id
    from .storage import SolverRevisionConflictError

    pending = run["state"].get("execution_mode_pending")
    if pending:
        calls = run["state"].get("calls", {})
        call_id = latest_retry_id(calls, pending["call_id"])
        record = calls.get(call_id)
        retry = run["state"].get("authorized_retry")
        if record and record["status"] == "completed":
            reply = deepcopy(record["response"])
        else:
            if record and (not retry or retry["call_id"] != call_id):
                raise CallInterrupted(run["run_id"], call_id)
            request = {**deepcopy(record["request"] if record else pending["request"]), "problem": problem}
            if record:
                run = harness.commit_event(run["run_id"], expected_revision=run["state_revision"],
                    event={"event_id": f"execution-mode-retry-{retry['new_call_id']}", "type": "execution_mode_dispatched"},
                    state_updates={"counters": {**run["state"]["counters"],
                        "model_calls": run["state"]["counters"]["model_calls"] + 1}})
            request["state_revision"] = run["state_revision"]
            reply = dict(harness.dispatch(run, harness._meta_port.complete, harness.prepare_request(run, request)))
    else:
        while True:
            run = harness.get_run(run["run_id"])
            try:
                run = harness.commit_event(run["run_id"], expected_revision=run["state_revision"],
                    event={"event_id": f"execution-mode-dispatched-{revision}", "type": "execution_mode_dispatched"},
                    state_updates={"execution_mode_pending": {"marker": marker, "call_id": request["call_id"],
                                                             "request": {k: deepcopy(v) for k, v in request.items() if k != "problem"}},
                        "counters": {**run["state"]["counters"],
                                     "model_calls": run["state"]["counters"]["model_calls"] + 1}})
                break
            except SolverRevisionConflictError:
                continue
        request["state_revision"] = run["state_revision"]
        reply = dict(harness.dispatch(run, harness._meta_port.complete, harness.prepare_request(run, request)))
    if reply.get("mode") not in {"keep", "serial", "population", "intervene"} or not isinstance(reply.get("reason"), str):
        raise ValueError("invalid_execution_mode_decision")
    run = harness.get_run(run["run_id"])
    while True:
        run = harness.get_run(run["run_id"])
        try:
            run = harness.commit_event(run["run_id"], expected_revision=run["state_revision"],
                event={"event_id": f"execution-mode-decided-{revision}", "type": "execution_mode_decided",
                       "mode": reply["mode"], "reason": redact(reply["reason"][:400])},
                state_updates={})
            break
        except SolverRevisionConflictError:
            continue
    return run, reply


def serial_checkpoint_view(state, *, expected_revision):
    """Export an immutable serial execution view with checked parent/route provenance.

    The caller must still CAS the parent revision and reserve the parent budget.
    This is an execution snapshot, never an evidence-adoption operation.
    """
    import hashlib

    from .faithful_intervention_records import FaithfulInterventionError
    from .population_evidence import validate_dependencies
    from .population_store import _canonical

    checkpoint = state.get("serial_checkpoint") or {}
    route = state.get("population", {}).get("routes", {}).get(checkpoint.get("route_id"))
    if (state.get("state_revision") != expected_revision
            or (state.get("execution_switch") or {}).get("current_mode") != "serial"
            or (state.get("execution_switch") or {}).get("status") != "switched"
            or not route or route.get("inflight_action_id")
            or route.get("revision") != checkpoint.get("route_revision")
            or checkpoint.get("config_hash") != state.get("config_hash")
            or checkpoint.get("specification_version") != state.get("specification_version")
            or not validate_dependencies(state, route.get("dependencies", []))[0]
            or hashlib.sha256(_canonical(route["snapshot"]).encode()).hexdigest() != checkpoint.get("snapshot_hash")):
        raise FaithfulInterventionError("serial_checkpoint_source_changed")
    view = deepcopy(route["snapshot"])
    view.update(population_policy={"enabled": False}, phase="STEP_EXECUTE",
                route_policy={**view.get("route_policy", {}), "enabled": True},
                state_revision=expected_revision,
                serial_checkpoint_source=deepcopy(checkpoint))
    return view
