"""Bounded validation and one explicit repair for generated plans."""

from .budget import budget_reason, stop
from .finalize import finish
from .plan import validate_plan


def generated_plan(harness, run, invoke, request, version, config):
    retries = 1 if config.get("features", {}).get("star_routing") is True else 0
    for attempt in range(retries + 1):
        reason = budget_reason(run["state"], config)
        if reason:
            return stop(harness, run, reason), None
        run, plan = invoke(
            run,
            {
                **request,
                "repair_attempt": attempt,
                "repair_instruction": "Repair the invalid plan; obey exact schema and earlier dependencies."
                if attempt
                else None,
            },
        )
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
        except (TypeError, ValueError):
            if attempt == retries:
                return finish(harness, run, "partial_aborted", kind), None
    return run, None
