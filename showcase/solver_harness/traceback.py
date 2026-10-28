"""Atomic trace-back archival and dependency invalidation."""

from copy import deepcopy


def transition_decision(run, state, decision):
    """Whether a persisted decision is the ruling this transition committed.

    A decision only grants execution authority while its Run, plan version, Plan
    Attempt and step match. Its revision must identify the committed ruling and
    intervention, not necessarily the latest revision: audit events can follow
    a ruling before recovery consumes it. History never re-executes.
    """
    return (
        isinstance(decision, dict)
        and decision.get("consumed") is None
        and decision.get("run_id") == run["run_id"]
        and decision.get("plan_version") == state["plan_version"]
        and decision.get("attempt_index") == state["attempt_index"]
        and decision.get("step_id") == state["current_step"]
        and type(decision.get("decided_at_revision")) is int
        and any(
            event["state_revision"] == decision["decided_at_revision"]
            and event["type"] == (
                "meta_guidance_decided" if "action_type" in decision else "meta_decided"
            )
            for event in run.get("events", [])
        )
        and any(
            all(record.get(key) == value for key, value in decision.items())
            for record in state.get("meta_interventions", [])
        )
    )


def apply_traceback(harness, run):
    """Apply only an explicit valid target; retain immutable failure snapshots."""
    state = run["state"]
    if state["phase"] not in ("TRACE_BACK", "STEP_VERIFY"):
        return run
    step_id = state["current_step"]
    verification = state["steps"].get(step_id, {}).get("verification", {})
    meta = state.get("meta_decision", {})
    guidance = state.get("meta_guidance_decision") or {}
    from_guidance = (
        state["phase"] == "TRACE_BACK"
        and guidance.get("action_type") == "trace_back"
        and transition_decision(run, state, guidance)
    )
    from_meta = state["phase"] == "TRACE_BACK" and (
        (meta.get("decision") == "TRACE_BACK" and transition_decision(run, state, meta))
        or from_guidance
    )
    if from_meta:
        verification = {
            **(guidance if from_guidance else meta),
            "verdict": "TRACE_BACK",
            "valid": True,
            "reason": guidance.get("rationale", "") if from_guidance else meta["reason_summary"],
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
    # Classified ledger entries share the accepted ledger's invalidation and
    # rescue semantics: their sources, receipts and dependencies participate in
    # the same closure, so dead outcomes never survive and valid ones do.
    accepted = state["accepted_results"]
    ledger = [
        item for item in state.get("verified_results_ledger", []) if isinstance(item, dict)
    ]
    accepted_count = len(accepted)
    results = [*accepted, *ledger]
    known = {step["step_id"] for step in steps} | {
        result["result_id"] for result in results if result.get("result_id")
    }
    invalid_records = set()
    for index, result in enumerate(results):
        dependencies = result.get("dependencies")
        unsupported = index < accepted_count and result.get("evidence_level") not in {
            "llm_reviewed", "tool_verified"
        }
        if (not isinstance(dependencies, list) or any(dep not in known for dep in dependencies)
            or unsupported
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
    dead = set()
    seen_dead = set()
    seen_live = set()
    for index, result in enumerate(results):
        if (
            index in invalid_records
            or result.get("source") in invalid
            or result.get("result_id") in invalid
            or invalid.intersection(result.get("dependencies") or [])
        ):
            dead.add(index)
            # The same outcome can be visible through both ledgers; it dies once.
            key = result.get("result_id")
            if isinstance(key, str):
                if key in seen_dead:
                    continue
                seen_dead.add(key)
            invalidated.append({**result, "invalidated": True})
        elif index < accepted_count:
            key = result.get("result_id")
            if isinstance(key, str):
                if key in seen_live:
                    continue
                seen_live.add(key)
            rescued.append(deepcopy(result))
    # Classified ledger entries keep their identity in the ledger: survivors
    # stay classified, dead ones carry the invalidation mark so no stale fact
    # can be revived later.
    ledger = [
        {**result, "invalidated": True} if index in dead else result
        for index, result in enumerate(results)
        if index >= accepted_count
    ]
    invalid_steps = invalid.intersection(step["step_id"] for step in steps)
    failure = {
        "kind": "trace_back",
        "triggered_by": "meta_guidance" if from_guidance else ("meta" if from_meta else "verifier"),
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
    # Record the consumption result on the ruling this archive actually executed;
    # a consumed ruling can never authorize a later transition again.
    ruling = guidance if from_guidance else meta
    decision_revision = ruling.get("decided_at_revision") if from_meta else None
    consumption = {
        "event_type": "trace_back_applied",
        "state_revision": run["state_revision"] + 1,
        "trace_back_to": target,
    }
    return harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={
            "event_id": f"trace-back-applied-{attempt}-{step_id}",
            "type": "trace_back_applied",
            "trace_back_to": target,
            "role": "meta" if from_meta else "step_verifier",
            "triggered_by": "meta_guidance" if from_guidance else ("meta" if from_meta else "verifier"),
            **({
                "action_type": "trace_back",
                "failure_type": guidance.get("failure_type"),
            } if from_guidance else {}),
            **({"decision_revision": decision_revision}
               if isinstance(decision_revision, int) else {}),
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
            "verified_results_ledger": ledger,
            "failure_records": [*state["failure_records"], failure],
            "confirmed_failures_ledger": [*state["confirmed_failures_ledger"], failure],
            **({"meta_guidance_decision": {**guidance, "consumed": consumption}}
               if from_guidance else {}),
            **({"meta_decision": {**meta, "consumed": consumption}}
               if from_meta and not from_guidance else {}),
        },
    )
