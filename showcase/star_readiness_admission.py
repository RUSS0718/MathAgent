"""Admission of one whole Run against the confirmed #97 batch envelope."""

import math

ROUND_LIMITS = {"logical_calls": 18, "http_attempts": 24, "problem_tool_calls": 4,
                "charged_tokens": 98304}


def admit_next_run(used, limits, *, remaining_seconds, preflights):
    """Return a stop reason unless the next Run and its preflight both fit."""
    for key, ceiling in ROUND_LIMITS.items():
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
    if remaining_seconds < seconds:
        return "round_wall_seconds_insufficient"
    if type(preflights) is not int or preflights < 0:
        return "round_budget_invalid"
    if preflights + 1 > 3:
        return "environment_preflight_insufficient"
    if used["problem_tool_calls"] + limits["problem_tool_calls"] + preflights + 1 > 7:
        return "environment_tool_budget_insufficient"
    return None
