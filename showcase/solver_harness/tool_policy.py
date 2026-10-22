"""Runtime-only same-run read operations; no executable tool registry."""

from collections.abc import Mapping
from typing import Any


def execute_tool_request(
    harness,
    run_id: str,
    *,
    role: str,
    tool: str,
    arguments: Mapping[str, Any] | None,
    config: Mapping[str, Any],
):
    run = harness.get_run(run_id)
    args = {} if arguments is None else dict(arguments)
    enabled = config.get("features", {}).get("skills") is True
    # Caller identity is fixed by the invocation; arguments may never redirect reads.
    cross_run = any(key in args and args[key] != run_id for key in ("run_id", "target_run_id"))
    allowed = (
        enabled
        and role in {"explore", "reasoner", "step_verifier", "whole_solution_verifier"}
        and tool in {"read_state", "read_ledger"}
        and not cross_run
        and not (set(args) - {"run_id", "target_run_id"})
    )
    if not allowed:
        reason = "cross_run_denied" if cross_run else "tool_not_allowed"
        harness.commit_event(
            run_id,
            expected_revision=run["state_revision"],
            event={
                "event_id": f"tool-denied-{run['state_revision']}",
                "type": "tool_request_rejected",
                "reason": reason,
            },
        )
        return {"ok": False, "reason": reason}
    state = run["state"]
    keys = (
        ("phase", "current_step", "plan_version", "counters")
        if tool == "read_state"
        else ("accepted_results", "verified_results_ledger", "confirmed_failures_ledger")
    )
    return {
        "ok": True,
        "state_revision": run["state_revision"],
        "result": {key: state[key] for key in keys if key in state},
    }
