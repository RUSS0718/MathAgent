"""Admission of one whole Run against the confirmed #97 batch envelope."""

import math

from .star_readiness_v7 import V7_DRAFT_VERSION, V7_ROUND_LIMITS, V7_RUN_LIMITS

ROUND_LIMITS = {"logical_calls": 18, "http_attempts": 24, "problem_tool_calls": 4,
                "charged_tokens": 98304}
V7_RUN_WALL_SECONDS = V7_RUN_LIMITS[0]["wall_seconds"]
V7_ROUND_WALL_SECONDS = V7_ROUND_LIMITS["wall_seconds"]
V7_PREFLIGHTS = V7_ROUND_LIMITS["environment_preflights"]
V7_TOOLS_INCLUDING_ENVIRONMENT = V7_ROUND_LIMITS["tools_including_environment"]
TOOLS_INCLUDING_ENVIRONMENT = 7


def admit_next_run(
    used, limits, *, remaining_seconds, preflights, runs=0, registration_version=None
):
    """Return a stop reason unless the next Run and its preflight both fit."""
    is_v7 = registration_version == V7_DRAFT_VERSION
    round_limits = V7_ROUND_LIMITS if is_v7 else ROUND_LIMITS
    if is_v7:
        if type(runs) is not int or runs < 0:
            return "round_budget_invalid"
        if runs + 1 > round_limits["runs"]:
            return "round_runs_insufficient"
    for key in ROUND_LIMITS:
        ceiling = round_limits[key]
        actual, requested = used.get(key), limits.get(key)
        if type(actual) is not int or type(requested) is not int or min(actual, requested) < 0:
            return "round_budget_invalid"
        if actual + requested > ceiling:
            return f"round_{key}_insufficient"
    seconds = limits.get("wall_seconds")
    if (type(seconds) not in (int, float) or type(remaining_seconds) not in (int, float)
            or not math.isfinite(seconds) or not math.isfinite(remaining_seconds)
            or seconds <= 0 or remaining_seconds <= 0):
        return "round_budget_invalid"
    if is_v7 and remaining_seconds > V7_ROUND_WALL_SECONDS:
        return "round_budget_invalid"
    if is_v7 and seconds > V7_RUN_WALL_SECONDS:
        return "round_wall_seconds_insufficient"
    if remaining_seconds < seconds:
        return "round_wall_seconds_insufficient"
    if type(preflights) is not int or preflights < 0:
        return "round_budget_invalid"

    tools_including_environment = (
        used["problem_tool_calls"] + limits["problem_tool_calls"] + preflights + 1
    )
    if is_v7:
        if tools_including_environment > V7_TOOLS_INCLUDING_ENVIRONMENT:
            return "environment_tool_budget_insufficient"
        if preflights + 1 > V7_PREFLIGHTS:
            return "environment_preflight_insufficient"
    else:
        if preflights + 1 > 3:
            return "environment_preflight_insufficient"
        if tools_including_environment > TOOLS_INCLUDING_ENVIRONMENT:
            return "environment_tool_budget_insufficient"
    return None
