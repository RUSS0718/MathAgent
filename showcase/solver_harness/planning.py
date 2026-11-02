"""Initial model-generated plan for the explicitly enabled v1.2 route."""

from .finalize import budget_reason, commit, dispatch, finish
from .plan import validate_plan


def generate_initial_plan(harness, run, *, problem, model_port, config):
    if run["state"]["phase"] != "PLAN" or not config.get("features", {}).get("final_generation"):
        return run
    reason = budget_reason(run["state"], config)
    if reason:
        return finish(harness, run, "partial_budget_exhausted", reason)
    if model_port is None:
        return run
    state = run["state"]
    previous_plan = state.get("plan")
    decision = state.get("meta_decision")
    consumption = decision.get("consumed") if isinstance(decision, dict) else None
    recovering_replan = (
        state.get("replan_count", 0) > 0
        and isinstance(previous_plan, dict)
        and previous_plan.get("version") != state["plan_version"]
        and isinstance(consumption, dict)
        and consumption.get("event_type") == "plan_archived"
        and consumption.get("plan_version") == state["plan_version"]
    )
    version = state["plan_version"] if recovering_replan else state["plan_version"] + 1
    request = {
        "role": "planner",
        "session_key": f"planner:{run['run_id']}:plan{version}",
        "problem": problem,
        "plan_version": version,
    }
    if recovering_replan:
        failures = state.get("failure_records", [])
        request.update(
            forbidden_directions=list(dict.fromkeys(
                direction for failure in failures
                for direction in failure.get("forbidden_directions", [])
            )),
            failure_records=failures,
            accepted_results=state["accepted_results"],
            rescued_results=state.get("rescued_results", []),
            reexploration_findings=state.get("reexploration_findings", []),
        )
    else:
        request.update(
            exploration_findings=state["exploration_findings"],
            preplan_hint=state.get("preplan_hint"),
            instruction="Return a Plan with version and 1..20 steps with step_id, title, objective and earlier-step depends_on references.",
        )
    if config.get("features", {}).get("star_routing") is True:
        from .plan_generation import generated_plan

        run, plan = generated_plan(
            harness,
            run,
            lambda current, request: dispatch(harness, current, model_port.complete, request),
            request,
            version,
            config,
        )
        if plan is None:
            return run
    else:
        run, plan = dispatch(
            harness,
            run,
            model_port.complete,
            request,
        )
        try:
            validate_plan(plan)
            if plan["version"] != version:
                raise ValueError("wrong_plan_version")
        except ValueError:
            return finish(harness, run, "partial_aborted", "invalid_initial_plan")
    if recovering_replan:
        from ..redaction import redact

        plan = redact(plan)
    updates = {
        "phase": "STEP_EXECUTE",
        "plan": plan,
        "plan_version": version,
        "current_step": plan["steps"][0]["step_id"],
    }
    if recovering_replan:
        updates["pending_guidance_task"] = None
    decision_revision = decision.get("decided_at_revision") if isinstance(decision, dict) else None
    details = {"plan_version": version} if recovering_replan else {}
    if recovering_replan and isinstance(decision_revision, int):
        details["decision_revision"] = decision_revision
    return commit(
        harness,
        run,
        "plan_replaced" if recovering_replan else "initial_plan_generated",
        updates,
        **details,
    )
