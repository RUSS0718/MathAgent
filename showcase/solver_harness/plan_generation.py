"""Bounded validation and one explicit repair for generated plans."""

from .budget import budget_reason, stop
from .finalize import finish
from .plan import validate_plan


def generated_plan(harness, run, invoke, request, version, config):
    retries = 1 if config.get("features", {}).get("star_routing") is True else 0
    repair = {}
    for attempt in range(retries + 1):
        reason = budget_reason(run["state"], config)
        if reason:
            return stop(harness, run, reason), None
        from .calls import CallInterrupted

        try:
            run, plan = invoke(
                run,
                {
                    **request,
                    **repair,
                    "repair_attempt": attempt,
                    "repair_instruction": "Repair the invalid plan; obey exact schema and earlier dependencies."
                    if attempt
                    else None,
                },
            )
        except CallInterrupted:
            latest = harness.get_run(run["run_id"])
            last = next(
                (
                    item
                    for item in reversed(latest["state"].get("calls", {}).values())
                    if item["role"] == "planner"
                ),
                {},
            )
            if last.get("error_category") not in {
                "invalid_role_schema",
                "invalid_json",
                "empty_response",
            }:
                raise
            run = harness.commit_event(
                latest["run_id"],
                expected_revision=latest["state_revision"],
                event={
                    "event_id": f"plan-parse-{latest['state_revision']}",
                    "type": "plan_parse_failed",
                    "call_id": last["call_id"],
                },
                state_updates={"status": "running"},
            )
            plan = None
        kind = (
            "PARSE_ERROR"
            if plan is None or not isinstance(plan, dict) or not plan
            else "PLAN_INVALID"
        )
        try:
            validate_plan(plan)
            if plan["version"] != version:
                raise ValueError("wrong_plan_version")
            return run, plan
        except (TypeError, ValueError) as exc:
            repair = {"invalid_plan": plan, "validation_error": str(exc)}
            if attempt == retries:
                return finish(harness, run, "partial_aborted", kind), None
    return run, None
