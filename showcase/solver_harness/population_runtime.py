"""WorkUnit scheduling transitions inside the existing product controller."""

import time
from collections.abc import Mapping
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextvars import copy_context
from copy import deepcopy

from .population_schedule import round_schedule
from .population_store import command


def prepare_population_plan(proposal, specification):
    """Validate and bind a proposal before computing its independent frontier."""
    from .plan import validate_plan
    from .routes import frontier_digest, plan_frontier, route_plan_error
    from .specification import bind_plan_work_units

    validate_plan(proposal)
    error = route_plan_error(proposal)
    if error:
        raise ValueError(error)
    bound, _ = bind_plan_work_units(proposal, specification)
    return bound, frontier_digest(plan_frontier(bound, specification))


def register_plans(harness, run, plan):
    """Register distinct, validated route snapshots before any WorkUnit dispatch."""
    from .specification import bind_plan_work_units

    existing_routes = run["state"]["population"]["routes"]
    proposals = [plan, *plan.get("alternative_plans", [])]
    primary = next(iter(existing_routes), None)
    for index, proposal in enumerate(proposals, len(existing_routes) + 1):
        try:
            bound, digest = prepare_population_plan(proposal, run["state"]["problem_spec"])
        except (TypeError, ValueError) as exc:
            if index == 1:
                from .finalize import finish

                return finish(harness, run, "partial_aborted", "invalid_population_primary_plan")
            run = harness.commit_event(
                run["run_id"], expected_revision=run["state_revision"],
                event={"event_id": f"population-plan-rejected-{index}",
                       "type": "population_plan_rejected", "reason": str(exc)},
            )
            continue
        if any(item["frontier_digest"] == digest
               for item in run["state"]["population"]["routes"].values()):
            continue
        rid = "route-" + digest[:20]
        primary = primary or rid
        ids = {step["step_id"]: f"{rid}:{step['step_id']}" for step in bound["steps"]}
        bound = {"version": index, "steps": [{
            **step, "step_id": ids[step["step_id"]],
            "depends_on": [ids[item] for item in step.get("depends_on", [])],
        } for step in bound["steps"]]}
        bound, units = bind_plan_work_units(bound, run["state"]["problem_spec"])
        snapshot = {key: deepcopy(value) for key, value in run["state"].items()
                    if key not in {"population", "population_policy", "calls", "session_registry"}}
        snapshot.update(plan=bound, plan_version=index, steps={}, current_step=bound["steps"][0]["step_id"],
                        phase="STEP_EXECUTE", status="running", work_units=units,
                        calls={}, session_registry={}, state_revision=0)
        run = command(harness, run["run_id"], "register_route", route_id=rid,
                      parent_route_id=None if rid == primary else primary,
                      frontier_digest=digest, snapshot=snapshot, dependencies=[])
    if existing_routes:
        return run
    return harness.commit_event(run["run_id"], expected_revision=run["state_revision"],
                                event={"event_id": "population-started", "type": "population_started"},
                                state_updates={"phase": "POPULATION"})


def _estimates(harness, run, route, problem):
    """Use the actual adapter payload, output cap, timeout and parent deadline."""
    from .finalize import _serialized_request_size
    from .route_budget import expansion_budget

    port = harness._model_port
    base = expansion_budget(harness, run, problem, port, {"role": "planner", "problem": problem})
    if base.get("preflight_valid") is not True:
        raise ValueError(base.get("stop_reason", "closing_reserve_unavailable"))
    local = {"run_id": run["run_id"], "state": route["snapshot"], "state_revision": route.get("revision", 0)}
    state = local["state"]
    step = next(s for s in state["plan"]["steps"] if s["step_id"] == state["current_step"])
    from . import reasoner_checkpoint

    checkpoint_mode = reasoner_checkpoint.enabled(harness._config)
    checkpoints = reasoner_checkpoint.current_checkpoints(state) if checkpoint_mode else []
    parent_checkpoint = checkpoints[-1] if checkpoints else None
    previous = state.get("steps", {}).get(step["step_id"], {})
    cap = port.adapter.max_tokens
    report_bound = {"argument": "x" * (cap * 4), "claims": [], "blocked": False}
    policy = run["state"]["population_policy"]
    retry_limit = policy.get("retry_limit", 1)
    if type(retry_limit) is not int or retry_limit < 1:
        raise ValueError("population_retry_policy_unavailable")
    retry_slots = max(1, retry_limit)
    challenges = policy.get("max_challenge_rounds", harness._config.get("max_challenge_rounds", 1))
    roles = ["reasoner", "step_verifier"] * (1 + challenges)
    # A protocol repair can consume one more logical request for either role.
    roles.extend(("reasoner", "step_verifier"))
    calls = []
    for role in roles:
        request = ({"role": role, "step": step, "problem": problem}
                   if role == "reasoner" else
                   {"role": role, "step": step, "problem": problem,
                    "report": report_bound, "original_problem": problem,
                    "challenge_history": [*previous.get("challenge_history", []),
                                          *[{"objection": "x" * 2048}] * challenges]})
        # Checkpoint fields select a different wire schema and carry variable context.
        if role == "reasoner" and checkpoint_mode:
            request = reasoner_checkpoint.request(
                request, call_id=f"population-estimate:{role}:{step['step_id']}",
                round_number=len(checkpoints) + 1, parent=parent_checkpoint,
                objection=previous.get("verification", {}).get("objection"),
                guidance=state.get("meta_guidance_decision"),
            )
            request.update(
                current_goal=step["objective"],
                valid_sources=[item for item in [*state.get("accepted_results", []),
                                                *state.get("verified_results_ledger", [])]
                               if isinstance(item, Mapping) and item.get("invalidated") is not True
                               and item.get("status") not in {"INVALIDATED", "invalidated"}],
                open_obligations=list(parent_checkpoint.get("gaps", [])) if parent_checkpoint else [],
            )
        if role == "reasoner":
            task = state.get("pending_guidance_task")
            if isinstance(task, str) and task.strip():
                request["specific_task"] = task
            if previous.get("challenge_history"):
                request.update(challenge_history=previous["challenge_history"],
                               objection=previous.get("verification", {}).get("objection", ""))
            if state.get("phase") == "CHALLENGE":
                request.update(report=previous.get("report", {}),
                               objection=previous.get("verification", {}).get("objection", ""),
                               suspected_false_claim=harness._config.get("features", {}).get("skills") is True)
        elif parent_checkpoint is not None:
            request.update(step_goal=step["objective"], checkpoint=parent_checkpoint)
        from .sessions import prepare_session

        _, request = prepare_session(local, {
            **request, "call_id": f"population-estimate:{role}:{step['step_id']}",
            "failure_records": state.get("failure_records", []),
            "rescued_results": state.get("rescued_results", []),
            "state_revision": local["state_revision"],
        })
        input_estimate = _serialized_request_size(
            harness, port, local, request, use_snapshot=True
        ) + 1_024
        calls.append({"role": role, "input_estimate": input_estimate,
                      "output_cap": cap, "http_attempts": retry_slots})
    reservation = {
        "calls": calls,
        "tokens": sum((item["input_estimate"] + item["output_cap"])
                      * item["http_attempts"] for item in calls),
        "model_calls": len(calls),
        "http_attempts": sum(item["http_attempts"] for item in calls),
        "tool_calls": 0,
        "time_seconds": len(calls) * retry_slots * policy["request_timeout_seconds"],
    }
    return reservation, {**base["closing_reserve"], "tool_calls": 0}


def _work(parent, database_path, run_id, rid, aid, problem):
    """Execute one existing WorkUnit on an independent connection; persist receipt first."""
    from .budget import HardBudgetStop
    from .calls import CallInterrupted
    from .challenge import run_plan
    from .harness import SolverHarness
    from .population_route import RouteHarness

    with SolverHarness(database_path=database_path, config=parent._config,
                       model_port=parent._model_port, verifier_port=parent._verifier_port,
                       meta_port=parent._meta_port, tool_port=parent._tool_port,
                       event_observer=parent._event_observer) as worker:
        worker._population_owner = deepcopy(parent._population_owner)
        local = RouteHarness(worker, run_id, rid, aid)
        result = local.get_run(run_id)
        status = "completed"
        try:
            result = run_plan(local, result, problem=problem, plan=result["state"]["plan"],
                              model_port=worker._model_port, verifier_port=worker._verifier_port,
                              max_rounds=worker._config.get("population_policy", {}).get(
                                  "max_challenge_rounds", worker._config.get("max_challenge_rounds", 3)),
                              max_model_calls=worker._config["max_model_calls"],
                              max_runtime_seconds=worker._config["max_total_duration_seconds"],
                              one_work_unit=True)
            if result["state"].get("status") in {"interrupted", "recovered_pending_validation"}:
                status = "unknown"
        except (CallInterrupted, HardBudgetStop):
            latest = local.get_run(run_id)
            status = _physical_outcome(latest, aid)
        except Exception:
            latest = local.get_run(run_id)
            status = _physical_outcome(latest, aid)
        command(worker, run_id, "outcome", action_id=aid, status=status)
        return aid


def _physical_outcome(run, action_id):
    calls = run["state"].get("calls", {}).values()
    if any(item.get("status") in {"dispatched", "streaming", "unknown_outcome"}
           and (item.get("action_id") == action_id
                or item.get("request", {}).get("population_action_id") == action_id)
           for item in calls):
        return "unknown"
    return "failed"


def _collect(harness, run):
    """Reuse completed actions, including a crash between receipt and acceptance."""
    for action in list(run["state"]["population"]["actions"].values()):
        if action.get("status") == "completed" and not action.get("accepted"):
            run = command(harness, run["run_id"], "accept", action_id=action["action_id"])
    for aid, future in list(harness._population_futures.items()):
        if future.done():
            future.result()
            del harness._population_futures[aid]
    return harness._state_store.get_run(run["run_id"])


def tick(harness, run, problem):
    """Dispatch a fair round and await its next completion, never all its results."""
    from ..run_control import check_control
    from .obligation_evidence import all_root_obligations_satisfied

    check_control()
    run = _collect(harness, run)
    run = _refresh_closing_reserve(harness, run, problem)
    if run["state"]["population"].get("paused_reason"):
        return harness.commit_event(
            run["run_id"], expected_revision=run["state_revision"],
            event={"event_id": f"population-shared-paused-{run['state_revision']}",
                   "type": "population_paused"},
            state_updates={"status": "interrupted"},
        )
    from .population_recovery import evidence_fingerprint

    rejected = run["state"]["population"].get("rejected_evidence", {})
    if (all_root_obligations_satisfied(run["state"].get("obligation_ledger", []))
            and rejected.get("evidence_hash") != evidence_fingerprint(run["state"])):
        return _freeze_finalization(harness, run)
    pop = run["state"]["population"]
    from .population_pressure import pressure_reason

    pressure = pressure_reason(harness._state_store._connection, run["state"])
    if pressure:
        run = command(harness, run["run_id"], "patch", updates={"paused_reason": pressure})
        return harness.commit_event(
            run["run_id"], expected_revision=run["state_revision"],
            event={"event_id": f"population-pressure-{run['state_revision']}",
                   "type": "population_paused"},
            state_updates={"status": "interrupted"},
        )
    serial_route = run["state"].get("execution_serial_route")
    scheduling = ({**pop, "routes": {serial_route: pop["routes"][serial_route]},
                   "round_members": [rid for rid in pop.get("round_members", []) if rid == serial_route],
                   "opportunities": [rid for rid in pop.get("opportunities", []) if rid == serial_route]}
                  if serial_route else pop)
    schedule = round_schedule(scheduling)
    run = command(harness, run["run_id"], "patch", updates=schedule)
    for rid in schedule["order"]:
        route = run["state"]["population"]["routes"][rid]
        try:
            from .population_evidence import prepare_adoption

            adoption, dependencies = prepare_adoption(run["state"], route["snapshot"])
            route = {**route, "snapshot": {**route["snapshot"], **adoption}}
            reservation, closing = _estimates(harness, run, route, problem)
            retry = route["snapshot"].get("authorized_retry")
            aid = (f"{rid}:retry:{retry['new_call_id']}" if isinstance(retry, dict)
                   else f"{rid}:work:{route.get('revision', 0)}")
            run = command(harness, run["run_id"], "admit", route_id=rid, action_id=aid,
                          reservation=reservation, closing_reserve=closing,
                          dependencies=dependencies, adopt_evidence=True)
        except ValueError as exc:
            if str(exc) == "population_adoption_changed":
                return harness._state_store.get_run(run["run_id"])
            if str(exc) == "population_capacity_exhausted":
                continue
            run = command(harness, run["run_id"], "patch", updates={"paused_reason": str(exc)})
            continue
        if not hasattr(harness, "_population_executor"):
            capacity = run["state"]["population_policy"]["capacity"]["max_inflight"]
            harness._population_executor = ThreadPoolExecutor(max_workers=capacity,
                                                             thread_name_prefix="population")
        db_path = harness._state_store._connection.execute("PRAGMA database_list").fetchone()[2]
        context = copy_context()
        harness._population_futures[aid] = harness._population_executor.submit(
            context.run, _work, harness, db_path, run["run_id"], rid, aid, problem)
    if harness._population_futures:
        wait(list(harness._population_futures.values()), timeout=30, return_when=FIRST_COMPLETED)
        run = _collect(harness, run)
        return command(harness, run["run_id"], "patch", updates={"last_observed_at": time.time()})
    run = harness._state_store.get_run(run["run_id"])
    if (run["state"]["population"].get("rejected_evidence")
            and all_root_obligations_satisfied(run["state"].get("obligation_ledger", []))):
        return _freeze_finalization(harness, run)
    return harness.commit_event(run["run_id"], expected_revision=run["state_revision"],
                                event={"event_id": f"population-paused-{run['state_revision']}",
                                       "type": "population_paused"},
                                state_updates={"status": "interrupted"})


def _freeze_finalization(harness, run):
    """Freeze one candidate cycle; finalization retains its existing retry bound."""
    run = command(harness, run["run_id"], "freeze", candidate={"revision": run["state_revision"]})
    from .population_final_commit import commit_finalization

    return commit_finalization(
        harness, run,
        {"event_id": f"population-final-{run['state_revision']}",
         "type": "population_final_ready"},
        {"phase": "FINAL_GENERATE", "status": "running"},
    )


def _refresh_closing_reserve(harness, run, problem):
    from .route_budget import expansion_budget

    estimate = expansion_budget(
        harness, run, problem, harness._model_port,
        {"role": "planner", "problem": problem,
         "population_policy": {"version": run["state"]["population_policy"]["version"]}},
    )
    if estimate.get("preflight_valid") is not True:
        from .population_store import command

        return command(harness, run["run_id"], "patch", updates={
            "paused_reason": estimate.get("stop_reason") or "closing_reserve_unavailable",
        })
    closing = estimate["closing_reserve"]
    if run["state"]["population"].get("closing_reserve") != closing:
        from .population_store import command

        return command(harness, run["run_id"], "patch", updates={"closing_reserve": closing})
    return run
