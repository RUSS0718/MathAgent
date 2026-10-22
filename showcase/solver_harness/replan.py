"""Bounded plan replacement and optional noncoding research delegation."""

from copy import deepcopy
from datetime import UTC, datetime

from ..redaction import redact
from .plan import validate_plan


def _commit(harness, run, kind, updates, **details):
    return harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={"event_id": f"{kind}-{run['state_revision']}", "type": kind, **details},
        state_updates=updates,
    )


def _budget(state, calls, seconds):
    elapsed = (datetime.now(UTC) - datetime.fromisoformat(state["created_at"])).total_seconds()
    if elapsed >= seconds:
        return "runtime_budget_exhausted"
    if state["counters"]["model_calls"] >= calls:
        return "model_call_budget_exhausted"
    return None


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
        reply = deepcopy(dict(port.complete(deepcopy(request))))
    except Exception:
        reply = {}
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
    decision = state["meta_decision"]
    rescued, excluded = _reusable(state)
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
    run = _commit(
        harness,
        run,
        "plan_archived",
        {
            "phase": "POST_REPLAN_REEXPLORE"
            if config.get("reexplore_after_replan", False)
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
        },
    )
    calls = config.get("max_model_calls", 2)
    seconds = config.get("max_total_duration_seconds", 3600)
    findings = []
    if config.get("reexplore_after_replan", False):
        run, findings = _research(harness, run, model_port, config, calls, seconds)
    reason = _budget(run["state"], calls, seconds)
    if reason:
        return _stop(harness, run, reason)
    failures = run["state"]["failure_records"]
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
        },
    )


def _research(harness, run, port, config, calls, seconds):
    limit = config.get("max_reexploration_tasks", 2)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit <= 8:
        raise ValueError("config.max_reexploration_tasks must be 0..8")
    # Reserve at least one global call for Planner; research is optional.
    if calls - run["state"]["counters"]["model_calls"] <= 1 or _budget(
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
            "forbidden_directions": run["state"]["meta_decision"]["forbidden_directions"],
        },
    )
    tasks = reply.get("tasks", [])
    if not isinstance(tasks, list):
        tasks = []
    records, findings = [], []
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
        if calls - run["state"]["counters"]["model_calls"] <= 1 or _budget(
            run["state"], calls, seconds
        ):
            break
        task_id = f"replan{run['state']['plan_version']}:task{number}"
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
        finding = {
            "task_id": task_id,
            "output": redact(output),
            "provenance": "unverified_exploration",
        }
        findings.append(finding)
        records.append(
            {
                "task_id": task_id,
                "parent_replan_id": run["state"]["plan_version"],
                "prompt": redact(task["prompt"]),
                "permitted_tools": [],
                "timeout_seconds": timeout,
                "status": "complete",
                "output_ref": task_id,
            }
        )
    return _commit(
        harness,
        run,
        "reexploration_completed",
        {
            "phase": "PLAN",
            "reexploration_tasks": [*run["state"]["reexploration_tasks"], *records],
            "reexploration_findings": findings,
        },
    ), findings


def _reusable(state):
    pending = deepcopy(state["accepted_results"])
    rescued = []
    valid_ids = set()
    old_steps = {step["step_id"] for step in state.get("plan", {}).get("steps", [])}
    while pending:
        found = []
        for result in pending:
            dependencies = result.get("dependencies")
            if (
                result.get("source") not in old_steps
                and result.get("evidence_level") in {"llm_reviewed", "tool_verified"}
                and isinstance(dependencies, list)
                and all(dependency in valid_ids for dependency in dependencies)
            ):
                rescued.append(result)
                if result.get("result_id"):
                    valid_ids.add(result["result_id"])
                found.append(result)
        if not found:
            break
        pending = [result for result in pending if result not in found]
    return rescued, [{**result, "invalidated": True} for result in pending]
