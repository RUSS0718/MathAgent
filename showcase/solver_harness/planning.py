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
    version = run["state"]["plan_version"] + 1
    if config.get("features", {}).get("star_routing") is True:
        from .plan_generation import generated_plan

        run, plan = generated_plan(
            harness,
            run,
            lambda current, request: dispatch(harness, current, model_port.complete, request),
            {
                "role": "planner",
                "session_key": f"planner:{run['run_id']}:plan{version}",
                "problem": problem,
                "plan_version": version,
                "exploration_findings": run["state"]["exploration_findings"],
                "preplan_hint": run["state"].get("preplan_hint"),
                "instruction": "Return a Plan with version and 1..20 steps with step_id, title, objective and earlier-step depends_on references.",
            },
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
            {
                "role": "planner",
                "session_key": f"planner:{run['run_id']}:plan{version}",
                "problem": problem,
                "plan_version": version,
                "exploration_findings": run["state"]["exploration_findings"],
                "preplan_hint": run["state"].get("preplan_hint"),
                "instruction": "Return a Plan with version and 1..20 steps with step_id, title, objective and earlier-step depends_on references.",
            },
        )
        try:
            validate_plan(plan)
            if plan["version"] != version:
                raise ValueError("wrong_plan_version")
        except ValueError:
            return finish(harness, run, "partial_aborted", "invalid_initial_plan")
    return commit(
        harness,
        run,
        "initial_plan_generated",
        {
            "phase": "STEP_EXECUTE",
            "plan": plan,
            "plan_version": version,
            "current_step": plan["steps"][0]["step_id"],
        },
    )
