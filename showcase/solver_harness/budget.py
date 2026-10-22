"""One hard-budget predicate shared by phase and dispatch boundaries."""

from datetime import UTC, datetime


def budget_reason(state, config):
    elapsed = (datetime.now(UTC) - datetime.fromisoformat(state["created_at"])).total_seconds()
    if elapsed >= config.get("max_total_duration_seconds", 3600):
        return "runtime_budget_exhausted"
    if state["counters"]["model_calls"] >= config.get("max_model_calls", 2):
        return "model_call_budget_exhausted"
    if (
        config.get("features", {}).get("local_code_tool") is True
        and config.get("allowed_tools")
        and state["counters"]["tool_calls"] >= config.get("max_tool_calls", 8)
    ):
        return "tool_call_budget_exhausted"
    return None


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
