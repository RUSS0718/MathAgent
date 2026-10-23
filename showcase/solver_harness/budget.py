"""One hard-budget predicate shared by phase and dispatch boundaries."""

import time
from datetime import UTC, datetime

from ..run_budget import current_budget


def budget_reason(state, config):
    shared = current_budget()
    if shared is not None:
        budget = shared.snapshot()
        if time.time() >= budget["deadline_at"]:
            return "runtime_budget_exhausted"
        if budget["logical_calls"] >= budget["limits"]["max_model_calls"]:
            return "model_call_budget_exhausted"
        if budget["http_attempts"] >= budget["limits"]["max_http_attempts"]:
            return "http_attempt_budget_exhausted"
        if budget["charged_tokens"] + budget["reserved_tokens"] >= budget["limits"]["max_tokens"]:
            return "token_budget_exhausted"
        if _tools_authorized(state, config) and budget["tool_calls"] >= budget["limits"]["max_tool_calls"]:
            return "tool_call_budget_exhausted"
        return None
    elapsed = (datetime.now(UTC) - datetime.fromisoformat(state["created_at"])).total_seconds()
    if elapsed >= config.get("max_total_duration_seconds", 3600):
        return "runtime_budget_exhausted"
    if state["counters"]["model_calls"] >= config.get("max_model_calls", 2):
        return "model_call_budget_exhausted"
    if (
        _tools_authorized(state, config)
        and state["counters"]["tool_calls"] >= config.get("max_tool_calls", 8)
    ):
        return "tool_call_budget_exhausted"
    return None


def _tools_authorized(state, config):
    return (state.get("reasoning_mode") != "reason_noncoding"
            and config.get("features", {}).get("local_code_tool") is True
            and bool(config.get("allowed_tools")))


def remaining_model_calls(state, config):
    shared = current_budget()
    if shared is not None:
        budget = shared.snapshot()
        return budget["limits"]["max_model_calls"] - budget["logical_calls"]
    return config.get("max_model_calls", 2) - state["counters"]["model_calls"]


class HardBudgetStop(BaseException):
    """Stop normalization and return the persisted terminal budget result."""

    def __init__(self, run_id):
        self.run_id = run_id


def stop(harness, run, reason):
    return harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={
            "event_id": f"hard-budget-{run['state_revision']}",
            "type": "budget_exhausted",
            "reason": reason,
        },
        state_updates={
            "phase": "TERMINAL",
            "status": "partial_budget_exhausted",
            "budget": {**run["state"].get("budget", {}), "exhaustion_reason": reason},
            "final_response": "Hard budget exhausted; no further model or tool calls are permitted.",
        },
    )
