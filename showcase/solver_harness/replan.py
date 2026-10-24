"""Bounded plan replacement and optional noncoding research delegation."""

from copy import deepcopy

from ..redaction import redact
from .budget import remaining_model_calls
from .plan import validate_plan
from .traceback import transition_decision


def replan_ruling(run, state):
    """The single APPROVE_REPLAN ruling that authorizes this archive-and-replace.

    Only the current transition's unconsumed Meta ruling grants execution
    authority (Run, plan version, Plan Attempt, step and committing revision all
    matching). A Guidance request never substitutes for the approval, so a stale
    replan Guidance cannot override or synthesize a later decision.
    """
    decision = state.get("meta_decision")
    if not isinstance(decision, dict) or decision.get("decision") != "APPROVE_REPLAN":
        return None
    if not transition_decision(run, state, decision):
        return None
    return decision


def _commit(harness, run, kind, updates, **details):
    return harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={"event_id": f"{kind}-{run['state_revision']}", "type": kind, **details},
        state_updates=updates,
    )


def _budget(state, calls, seconds):
    from .budget import budget_reason

    return budget_reason(state, {"max_model_calls": calls, "max_total_duration_seconds": seconds})


def _stop(harness, run, reason):
    return _commit(
        harness,
        run,
        "replan_stopped",
        {
            "phase": "TERMINAL",
            "status": "partial_budget_exhausted" if "budget" in reason else "partial_aborted",
            "budget": {**run["state"].get("budget", {}), "exhaustion_reason": reason},
            "final_response": f"Replanning stopped: {reason}; no verified final answer is available.",
        },
        reason=reason,
    )


def _call(harness, run, port, request):
    state = run["state"]
    request = {
        "run_id": run["run_id"],
        "call_id": f"replan:{run['run_id']}:plan{state['plan_version']}:attempt{state['attempt_index']}:{run['state_revision']}",
        "allowed_tools": [],
        "tool_policy": {"allow": []},
        **request,
    }
    run = _commit(
        harness,
        run,
        "replan_dispatched",
        {"counters": {**state["counters"], "model_calls": state["counters"]["model_calls"] + 1}},
        role=request["role"],
    )
    try:
        request = harness.prepare_request(run, request)
        request.update(allowed_tools=[], tool_policy={"allow": []})
        operation = port.complete
        if request["role"] == "researcher":
            from .research import bounded_research

            def operation(prepared):
                return bounded_research(port.complete, prepared)

        reply = deepcopy(dict(harness.dispatch(run, operation, request)))
    except Exception as exc:
        reply = (
            {"_research_status": getattr(exc, "research_status", "failed")}
            if request["role"] == "researcher"
            else {}
        )
    return run, reply


def run_replan(harness, run, *, problem, model_port, config):
    """Archive before dispatch; a planner response must be an executable new Plan."""
    if run["state"]["phase"] != "REPLAN" or model_port is None:
        return run
    state = run["state"]
    limit = config.get("max_replans", 3)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError("config.max_replans must be a non-negative integer")
    if state.get("replan_count", 0) >= limit:
        return _stop(harness, run, "replan_limit_reached")
    decision = replan_ruling(run, state)
    if decision is None:
        # Expired, consumed or missing approval: record it and hand the decision
        # back to Meta instead of silently archiving on a stale ruling.
        return harness.commit_event(
            run["run_id"],
            expected_revision=run["state_revision"],
            event={
                "event_id": f"replan-unauthorized-{run['state_revision']}",
                "type": "replan_unauthorized",
                "reason": "missing_valid_replan_ruling",
            },
            state_updates={
                "phase": "META_DECIDE",
                "meta_interventions": [
                    *state["meta_interventions"],
                    {
                        "trigger": "UNAUTHORIZED_REPLAN_TRANSITION",
                        "plan_version": state["plan_version"],
                        "attempt_index": state["attempt_index"],
                        "step_id": state["current_step"],
                    },
                ],
            },
        )
    rescued, excluded = _reusable(state, decision)
    failure = {
        "kind": "replan",
        "plan_version": state["plan_version"],
        "attempt_index": state["attempt_index"],
        "archived_plan": deepcopy(state.get("plan")),
        "archived_steps": deepcopy(state["steps"]),
        "invalidated_results": excluded,
        "rescued_results": rescued,
        "reason": decision["reason_summary"],
        "forbidden_directions": decision["forbidden_directions"],
    }
    version = state["plan_version"] + 1
    # Record the consumption result on the ruling this archive executes; a consumed
    # ruling can never authorize a later transition again, and recovery never
    # re-archives an already-archived plan.
    consumption = {
        "event_type": "plan_archived",
        "state_revision": run["state_revision"] + 1,
        "plan_version": version,
    }
    ruling_revision = decision.get("decided_at_revision")
    run = _commit(
        harness,
        run,
        "plan_archived",
        {
            "phase": "POST_REPLAN_REEXPLORE"
            if config.get("features", {}).get(
                "reexplore_after_replan", config.get("reexplore_after_replan", False)
            )
            else "PLAN",
            "replan_count": state.get("replan_count", 0) + 1,
            "plan_version": version,
            "attempt_index": state["attempt_index"] + 1,
            "failure_records": [*state["failure_records"], failure],
            "confirmed_failures_ledger": [*state["confirmed_failures_ledger"], failure],
            "accepted_results": rescued,
            "rescued_results": rescued,
            "steps": {},
            "current_step": None,
            "meta_decision": {**decision, "consumed": consumption},
        },
        archived_plan_version=state["plan_version"],
        archived_step_count=len(state["steps"]),
        invalidated_result_count=len(excluded),
        rescued_result_count=len(rescued),
        **({"decision_revision": ruling_revision} if isinstance(ruling_revision, int) else {}),
    )
    calls = config.get("max_model_calls", 2)
    seconds = config.get("max_total_duration_seconds", 3600)
    findings = []
    if config.get("features", {}).get(
        "reexplore_after_replan", config.get("reexplore_after_replan", False)
    ):
        run, findings = _research(
            harness, run, model_port, config, calls, seconds,
            decision.get("forbidden_directions", []),
        )
    reason = _budget(run["state"], calls, seconds)
    if reason:
        return _stop(harness, run, reason)
    failures = run["state"]["failure_records"]
    if config.get("features", {}).get("star_routing") is True:
        from .plan_generation import generated_plan

        run, plan = generated_plan(
            harness,
            run,
            lambda current, request: _call(harness, current, model_port, request),
            {
                "role": "planner",
                "session_key": f"planner:{run['run_id']}:plan{version}",
                "problem": problem,
                "plan_version": version,
                "forbidden_directions": list(
                    dict.fromkeys(d for f in failures for d in f.get("forbidden_directions", []))
                ),
                "failure_records": failures,
                "accepted_results": run["state"]["accepted_results"],
                "rescued_results": run["state"].get("rescued_results", []),
                "reexploration_findings": findings,
            },
            version,
            config,
        )
        if plan is None:
            return run
    else:
        run, plan = _call(
            harness,
            run,
            model_port,
            {
                "role": "planner",
                "session_key": f"planner:{run['run_id']}:plan{version}",
                "problem": problem,
                "plan_version": version,
                "forbidden_directions": list(
                    dict.fromkeys(d for f in failures for d in f.get("forbidden_directions", []))
                ),
                "failure_records": failures,
                "accepted_results": run["state"]["accepted_results"],
                "rescued_results": run["state"].get("rescued_results", []),
                "reexploration_findings": findings,
            },
        )
        try:
            validate_plan(plan)
            if plan["version"] != version:
                raise ValueError("wrong_plan_version")
        except ValueError:
            return _stop(harness, run, "invalid_replacement_plan")
    return _commit(
        harness,
        run,
        "plan_replaced",
        {
            "phase": "STEP_EXECUTE",
            "plan": redact(plan),
            "current_step": plan["steps"][0]["step_id"],
            "pending_guidance_task": None,
        },
        plan_version=version,
        **({"decision_revision": ruling_revision} if isinstance(ruling_revision, int) else {}),
    )


def _research(harness, run, port, config, calls, seconds, forbidden_directions):
    limit = config.get("max_reexploration_tasks", 2)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit <= 8:
        raise ValueError("config.max_reexploration_tasks must be 0..8")
    # Reserve at least one global call for Planner; research is optional.
    if remaining_model_calls(run["state"], {"max_model_calls": calls}) <= 1 or _budget(
        run["state"], calls, seconds
    ):
        return _commit(
            harness, run, "reexploration_skipped", {"phase": "PLAN"}, reason="skip_due_to_budget"
        ), []
    run, reply = _call(
        harness,
        run,
        port,
        {
            "role": "meta",
            "action": "delegate_research_task",
            "session_key": f"meta:{run['run_id']}",
            "max_tasks": limit,
            "forbidden_directions": forbidden_directions,
        },
    )
    tasks = reply.get("tasks", [])
    if not isinstance(tasks, list):
        tasks = []
    findings = []
    for number, task in enumerate(tasks[:limit]):
        if (
            not isinstance(task, dict)
            or not isinstance(task.get("prompt"), str)
            or not task["prompt"].strip()
            or task.get("permitted_tools", []) != []
        ):
            continue
        timeout = task.get("timeout_seconds", 60)
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 300:
            continue
        if remaining_model_calls(run["state"], {"max_model_calls": calls}) <= 1 or _budget(
            run["state"], calls, seconds
        ):
            break
        task_id = f"replan{run['state']['plan_version']}:task{number}"
        record = {
            "task_id": task_id,
            "parent_replan_id": run["state"]["plan_version"],
            "prompt": redact(task["prompt"]),
            "permitted_tools": [],
            "timeout_seconds": timeout,
            "status": "running",
            "output_ref": None,
        }
        run = _commit(
            harness,
            run,
            "research_started",
            {"reexploration_tasks": [*run["state"]["reexploration_tasks"], record]},
        )
        try:
            run, output = _call(
                harness,
                run,
                port,
                {
                    "role": "researcher",
                    "timeout_seconds": timeout,
                    "session_key": f"research:{run['run_id']}:{task_id}",
                    "task": {**task, "permitted_tools": [], "timeout_seconds": timeout},
                },
            )
        except BaseException:
            import sys

            from .calls import CallInterrupted

            if isinstance(sys.exception(), CallInterrupted):
                latest = harness.get_run(run["run_id"])
                call = next(
                    (
                        item
                        for item in reversed(latest["state"].get("calls", {}).values())
                        if item.get("role") == "researcher"
                    ),
                    {},
                )
                status = (
                    "unknown_outcome"
                    if call.get("error_type") in {"TimeoutError", "FutureTimeoutError"}
                    else "failed"
                )
                _commit(
                    harness,
                    latest,
                    "research_interrupted",
                    {
                        "reexploration_tasks": [
                            *latest["state"]["reexploration_tasks"][:-1],
                            {**record, "status": status},
                        ]
                    },
                )
            raise
        status = output.pop("_research_status", "complete" if output else "failed")
        record.update(status=status, output_ref=task_id if status == "complete" else None)
        run = _commit(
            harness,
            run,
            "research_finished",
            {"reexploration_tasks": [*run["state"]["reexploration_tasks"][:-1], record]},
        )
        if status == "complete":
            findings.append(
                {
                    "task_id": task_id,
                    "output": redact(output),
                    "provenance": "unverified_exploration",
                }
            )
    return _commit(
        harness,
        run,
        "reexploration_completed",
        {
            "phase": "PLAN",
            "reexploration_tasks": run["state"]["reexploration_tasks"],
            "reexploration_findings": findings,
        },
    ), findings


def _reusable(state, decision=None):
    pending = deepcopy(state["accepted_results"])
    rescued = []
    valid_ids = set()
    old_steps = {step["step_id"] for step in state.get("plan", {}).get("steps", [])}
    selected = (decision or {}).get("reusable_results", [])
    invalidated = [result for failure in state.get("failure_records", [])
                   for result in failure.get("invalidated_results", [])]
    invalid_refs = {value for result in invalidated
                    for value in (result.get("result_id"), result.get("source")) if value}
    while pending:
        found = []
        for result in pending:
            dependencies = result.get("dependencies")
            if (
                (result.get("source") not in old_steps
                 or result.get("result_id") in selected
                 or result.get("statement") in selected)
                and result.get("valid", True)
                and not result.get("invalidated", False)
                and result.get("status") not in {"INVALIDATED", "invalidated"}
                and not any(
                    (result.get("result_id") and result.get("result_id") == item.get("result_id"))
                    or (result.get("statement") == item.get("statement")
                        and result.get("source") == item.get("source"))
                    for item in invalidated
                )
                and result.get("evidence_level") in {"llm_reviewed", "tool_verified"}
                and isinstance(dependencies, list)
                and not invalid_refs.intersection(dependencies)
                and all(dependency in valid_ids for dependency in dependencies)
            ):
                rescued.append(result)
                if result.get("result_id"):
                    valid_ids.add(result["result_id"])
                if result.get("source"):
                    valid_ids.add(result["source"])
                found.append(result)
        if not found:
            break
        pending = [result for result in pending if result not in found]
    return rescued, [{**result, "invalidated": True} for result in pending]
