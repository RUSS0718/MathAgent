"""Atomic trace-back archival and dependency invalidation."""

from copy import deepcopy


def apply_traceback(harness, run):
    """Apply only an explicit valid target; retain immutable failure snapshots."""
    state = run["state"]
    if state["phase"] not in ("TRACE_BACK", "STEP_VERIFY"):
        return run
    step_id = state["current_step"]
    verification = state["steps"].get(step_id, {}).get("verification", {})
    meta = state.get("meta_decision", {})
    from_meta = state["phase"] == "TRACE_BACK" and meta.get("decision") == "TRACE_BACK"
    if from_meta:
        verification = {
            **meta,
            "verdict": "TRACE_BACK",
            "valid": True,
            "reason": meta["reason_summary"],
        }
    if verification.get("verdict") != "TRACE_BACK":
        return run
    target = verification.get("trace_back_to")
    steps = state["plan"]["steps"]
    current = next(i for i, step in enumerate(steps) if step["step_id"] == step_id)
    valid = (
        verification.get("valid")
        and isinstance(target, int)
        and not isinstance(target, bool)
        and 1 <= target <= current + 1
    )
    attempt = state["attempt_index"]
    if not valid:
        return harness.commit_event(
            run["run_id"],
            expected_revision=run["state_revision"],
            event={
                "event_id": f"trace-back-invalid-{attempt}-{step_id}",
                "type": "trace_back_invalid",
                "trigger": "INVALID_TRACE_BACK_TARGET",
            },
            state_updates={
                "phase": "META_DECIDE",
                "meta_interventions": [
                    *state["meta_interventions"],
                    {
                        "trigger": "INVALID_TRACE_BACK_TARGET",
                        "step_id": step_id,
                        "trace_back_to": target,
                    },
                ],
            },
        )
    archived_ids = {step["step_id"] for step in steps[target - 1 : current + 1]}
    invalid = set(archived_ids)
    results = state["accepted_results"]
    known = {step["step_id"] for step in steps} | {
        result["result_id"] for result in results if result.get("result_id")
    }
    invalid_records = set()
    for index, result in enumerate(results):
        dependencies = result.get("dependencies")
        if (not isinstance(dependencies, list) or any(dep not in known for dep in dependencies)
            or result.get("evidence_level") not in {"llm_reviewed", "tool_verified"}
            or not result.get("valid", True) or result.get("invalidated", False)
            or result.get("status") in {"INVALIDATED", "invalidated"}):
            invalid_records.add(index)
            if result.get("result_id"):
                invalid.add(result["result_id"])
            elif result.get("source"):
                invalid.add(result["source"])
    # Both step IDs and result IDs may be dependency references.
    changed = True
    while changed:
        before = set(invalid)
        for step in steps:
            if invalid.intersection(step.get("depends_on", [])):
                invalid.add(step["step_id"])
        for result in results:
            if result.get("source") in invalid or invalid.intersection(
                result.get("dependencies") or []
            ):
                if result.get("result_id"):
                    invalid.add(result["result_id"])
        changed = before != invalid
    invalidated = []
    rescued = []
    for index, result in enumerate(results):
        if (
            index in invalid_records
            or result.get("source") in invalid
            or result.get("result_id") in invalid
            or invalid.intersection(result.get("dependencies") or [])
        ):
            invalidated.append({**result, "invalidated": True})
        else:
            rescued.append(deepcopy(result))
    invalid_steps = invalid.intersection(step["step_id"] for step in steps)
    failure = {
        "kind": "trace_back",
        "triggered_by": "meta" if from_meta else "verifier",
        "reason": verification.get("reason") or verification.get("objection", ""),
        "forbidden_directions": verification.get("forbidden_directions", []),
        "plan_version": state["plan_version"],
        "attempt_index": attempt,
        "from_step": step_id,
        "trace_back_to": target,
        "archived_steps": deepcopy(
            {key: value for key, value in state["steps"].items() if key in invalid_steps}
        ),
        "invalidated_results": invalidated,
        "rescued_results": rescued,
    }
    return harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={
            "event_id": f"trace-back-applied-{attempt}-{step_id}",
            "type": "trace_back_applied",
            "trace_back_to": target,
            "attempt_index": attempt + 1,
            "from_step_index": current + 1,
            "archived_step_count": sum(key in invalid_steps for key in state["steps"]),
            "invalidated_result_count": len(invalidated),
            "rescued_result_count": len(rescued),
        },
        state_updates={
            "phase": "STEP_EXECUTE",
            "current_step": steps[target - 1]["step_id"],
            "attempt_index": attempt + 1,
            "steps": {
                key: value for key, value in state["steps"].items() if key not in invalid_steps
            },
            "accepted_results": rescued,
            "rescued_results": rescued,
            "failure_records": [*state["failure_records"], failure],
            "confirmed_failures_ledger": [*state["confirmed_failures_ledger"], failure],
        },
    )
