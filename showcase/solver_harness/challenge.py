"""Same-step objection replies with bounded verifier sessions."""

from collections.abc import Mapping

from . import protocol_repair, reasoner_checkpoint
from .budget import budget_reason
from .calls import CallInterrupted
from .finalize import finish
from .step import _normalize_report, run_step
from .traceback import apply_traceback, transition_decision
from .verification import verify_step


def run_challenges(
    harness,
    run,
    *,
    problem,
    model_port,
    verifier_port,
    max_rounds,
    max_model_calls,
    max_runtime_seconds,
):
    """Reply and recheck in verify:{run_id}:plan{version}:step{step_id}."""
    from .progress import guard_action

    run = guard_action(harness, run)
    if run["state"]["phase"] == "TERMINAL":
        return run
    initial_state = run["state"]
    step_id = initial_state["current_step"]
    initial_history = initial_state["steps"].get(step_id, {}).get("challenge_history", [])
    completed_rounds = max(
        (
            item["round"]
            for item in initial_history
            if isinstance(item, dict)
            and type(item.get("round")) is int
            and item["round"] > 0
        ),
        default=0,
    )
    for number in range(completed_rounds + 1, max_rounds + 1):
        state = run["state"]
        if state["phase"] != "CHALLENGE":
            return run
        run = guard_action(harness, run)
        if run["state"]["phase"] == "TERMINAL":
            return run
        attempt = state["attempt_index"]
        suffix = f"-attempt-{attempt}" if attempt else ""
        step_id = state["current_step"]
        record = state["steps"][step_id]
        checkpoint_mode = reasoner_checkpoint.enabled(harness._config)
        checkpoints = reasoner_checkpoint.current_checkpoints(state) if checkpoint_mode else []
        parent_checkpoint = checkpoints[-1] if checkpoints else None
        if checkpoint_mode and len(checkpoints) >= reasoner_checkpoint.MAX_CHECKPOINT_ROUNDS:
            return finish(harness, run, "partial_aborted", "reasoner_checkpoint_round_limit")
        session = f"verify:{run['run_id']}:plan{state['plan_version']}:step{step_id}{suffix}"
        reason = budget_reason(state, {"max_model_calls": max_model_calls,
                                       "max_total_duration_seconds": max_runtime_seconds})
        if reason:
            return harness.commit_event(
                run["run_id"],
                expected_revision=run["state_revision"],
                event={
                    "event_id": f"challenge-budget-{step_id}-{number}{suffix}",
                    "type": "budget_exhausted",
                    "reason": reason,
                },
                state_updates={
                    "budget": {**state.get("budget", {}), "exhaustion_reason": reason},
                    "status": "partial_budget_exhausted",
                    "final_response": "Budget exhausted during challenge; no verified answer is available.",
                },
            )
        step = next(s for s in state["plan"]["steps"] if s["step_id"] == step_id)
        objection = record["verification"]["objection"]
        if not objection.strip():
            return harness.commit_event(
                run["run_id"],
                expected_revision=run["state_revision"],
                event={
                    "event_id": f"challenge-invalid-{step_id}-{number}{suffix}",
                    "type": "challenge_invalid",
                    "reason": "missing_objection",
                },
                state_updates={
                    "phase": "STEP_VERIFY",
                    "steps": {
                        **state["steps"],
                        step_id: {
                            **record,
                            "verification": {
                                **record["verification"],
                                "valid": False,
                                "reason": "missing_objection",
                            },
                        },
                    },
                },
            )
        counters = {**state["counters"], "model_calls": state["counters"]["model_calls"] + 1}
        run = harness.commit_event(
            run["run_id"],
            expected_revision=run["state_revision"],
            event={
                "event_id": f"challenge-dispatched-{step_id}-{number}{suffix}",
                "type": "challenge_dispatched",
                "round": number,
                "role": "reasoner",
            },
            state_updates={"counters": counters},
        )
        base_request = {
            "role": "reasoner",
            "run_id": run["run_id"],
            "problem": problem,
            "call_id": (
                f"{run['run_id']}:reasoner:checkpoint:{state['plan_version']}:{step_id}:"
                f"{len(checkpoints) + 1}:challenge-{number}{suffix}"
                if checkpoint_mode else f"{session}:reasoner:{number}"
            ),
            "session_key": session,
            "step": step,
            "report": record["report"],
            "objection": objection,
            "round": number,
            "challenge_history": record.get("challenge_history", []),
            "tool_policy": {"allow": []},
        }
        request = base_request
        if checkpoint_mode:
            request = reasoner_checkpoint.request(
                base_request,
                call_id=base_request["call_id"],
                round_number=len(checkpoints) + 1,
                parent=parent_checkpoint,
                objection=objection,
                guidance=state.get("meta_guidance_decision"),
            )
            request.update({
                "current_goal": step["objective"],
                "valid_sources": [
                    item for item in [
                        *state.get("accepted_results", []),
                        *state.get("verified_results_ledger", []),
                    ]
                    if isinstance(item, Mapping)
                    and item.get("invalidated") is not True
                    and item.get("status") not in {"INVALIDATED", "invalidated"}
                ],
                "open_obligations": list(parent_checkpoint.get("gaps", []))
                if parent_checkpoint else [],
            })
        if harness._config.get("features", {}).get("skills") is True:
            request["suspected_false_claim"] = True
        try:
            reply = harness.dispatch(
                run,
                model_port.complete,
                request,
            )
        except CallInterrupted as exc:
            run = protocol_repair.reserve_repair(
                harness, run["run_id"], exc,
                failure_event=lambda latest, failed: {
                    "event_id": f"challenge-parse-{step_id}-{number}{suffix}-{latest['state_revision']}",
                    "type": "reasoner_parse_failed", "step_id": step_id, "role": "reasoner",
                },
                dispatch_event={
                    "event_id": f"challenge-dispatched-{step_id}-{number}{suffix}-repair-1",
                    "type": "challenge_dispatched", "round": number, "role": "reasoner",
                },
            )
            reply = harness.dispatch(
                run, model_port.complete, protocol_repair.repair_request(
                    request, failed_call=protocol_repair.interrupted_call(harness, run["run_id"], exc)),
            )
        except Exception:
            reply = {"blocked": True}
        checkpoint = None
        if checkpoint_mode:
            try:
                checkpoint = reasoner_checkpoint.parse(reply)
            except ValueError as exc:
                return finish(harness, harness.get_run(run["run_id"]), "partial_aborted", str(exc))
            if checkpoint["objective"] != step["objective"]:
                return finish(harness, harness.get_run(run["run_id"]), "partial_aborted", "invalid_reasoner_checkpoint_objective")
            if any(item.get("checkpoint_id") == checkpoint["checkpoint_id"]
                   for item in checkpoints):
                return finish(harness, harness.get_run(run["run_id"]), "partial_aborted", "reasoner_checkpoint_no_progress")
            if parent_checkpoint is not None and (
                checkpoint["checkpoint_id"] == parent_checkpoint["checkpoint_id"]
                or reasoner_checkpoint.same_draft(checkpoint, parent_checkpoint)
            ):
                return finish(harness, harness.get_run(run["run_id"]), "partial_aborted", "reasoner_checkpoint_no_progress")
            report = reasoner_checkpoint.to_report(checkpoint, step)
            if checkpoint["status"] in {"BLOCKED", "FAILED"}:
                report["blocked"] = True
        else:
            report = _normalize_report(reply, step)
        history = [
            *record.get("challenge_history", []),
            {
                "round": number,
                "session_key": session,
                "objection": objection,
                "reasoner_reply": report,
                "verdict": None,
                **({"checkpoint_id": checkpoint["checkpoint_id"]} if checkpoint else {}),
            },
        ]
        checkpoint_record = None
        if checkpoint is not None:
            checkpoint_record = reasoner_checkpoint.record(
                run,
                checkpoint,
                call_id=request["call_id"],
                checkpoint_round=len(checkpoints) + 1,
                plan_version=state["plan_version"],
                attempt_index=attempt,
                step_id=step_id,
                parent=parent_checkpoint,
            )
        run = harness.commit_event(
            run["run_id"],
            expected_revision=run["state_revision"],
            event={
                "event_id": f"challenge-replied-{step_id}-{number}{suffix}",
                "type": "challenge_replied",
                "round": number,
                "role": "reasoner",
            },
            state_updates={
                "phase": "STEP_VERIFY",
                "steps": {
                    **state["steps"],
                    step_id: {
                        **record,
                        "report": report,
                        "challenge_history": history,
                        **({
                            "checkpoint_status": checkpoint["status"],
                            "checkpoint_round": len(checkpoints) + 1,
                            "checkpoint_id": checkpoint["checkpoint_id"],
                        } if checkpoint else {}),
                    },
                },
                **({
                    "reasoner_checkpoints": [
                        *state.get("reasoner_checkpoints", []), checkpoint_record
                    ]
                } if checkpoint_record else {}),
            },
        )
        run = verify_step(
            harness,
            run,
            problem=problem,
            verifier_port=verifier_port,
            max_model_calls=max_model_calls,
            max_runtime_seconds=max_runtime_seconds,
            round_number=number,
        )
        updated = run["state"]["steps"][step_id]
        history[-1]["verdict"] = (
            updated.get("checkpoint_verification", updated["verification"])
            if run["state"]["phase"] != "TERMINAL" else None
        )
        run = harness.commit_event(
            run["run_id"],
            expected_revision=run["state_revision"],
            event={
                "event_id": f"challenge-recorded-{step_id}-{number}{suffix}",
                "type": "challenge_recorded",
                "round": number,
            },
            state_updates={
                "steps": {
                    **run["state"]["steps"],
                    step_id: {**updated, "challenge_history": history},
                }
            },
        )
    if run["state"]["phase"] != "CHALLENGE":
        return run
    state = run["state"]
    plan_version = state["plan_version"]
    attempt = state["attempt_index"]
    escalated = any(
        item.get("meta_trigger", item.get("trigger")) == "challenge_round_limit"
        and item.get("step_id") == step_id
        and item.get("plan_version") == plan_version
        and item.get("attempt_index") == attempt
        and item.get("decision") in {"CONTINUE", "TRACE_BACK", "APPROVE_REPLAN", "ABORT"}
        for item in state.get("meta_interventions", [])
    )
    if escalated:
        return harness.commit_event(
            run["run_id"],
            expected_revision=run["state_revision"],
            event={
                "event_id": f"challenge-escalation-stopped-{step_id}-{plan_version}-{attempt}-{state['state_revision']}",
                "type": "challenge_escalation_stopped",
                "upgrade_reason": "meta_escalation_limit_reached",
                "role": "controller",
            },
            state_updates={
                "phase": "TERMINAL",
                "status": "partial_aborted",
                "result_reason": "challenge_meta_limit_reached",
                "final_response": "Challenge limit reached after the bounded Meta continuation; no verified answer is available.",
            },
        )
    return harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={
            "event_id": f"challenge-stalemate-{step_id}-{plan_version}-{attempt}-{state['state_revision']}",
            "type": "challenge_stalemate",
            "trigger": "STALEMATE",
            "action": "META_DECIDE",
            "upgrade_reason": "round_limit_reached",
            "role": "controller",
        },
        state_updates={
            "phase": "META_DECIDE",
            "steps": {
                **state["steps"],
                step_id: {**state["steps"][step_id], "status": "STALEMATE"},
            },
            "meta_interventions": [
                *state["meta_interventions"],
                {
                    "trigger": "STALEMATE",
                    "meta_trigger": "challenge_round_limit",
                    "action": "META_DECIDE",
                    "upgrade_reason": "round_limit_reached",
                    "plan_version": plan_version,
                    "attempt_index": attempt,
                    "step_id": step_id,
                },
            ],
        },
    )


def run_plan(
    harness,
    run,
    *,
    problem,
    plan,
    model_port,
    verifier_port,
    max_rounds,
    max_model_calls,
    max_runtime_seconds,
):
    """Execute at most the supplied plan, preserving the final review boundary."""
    while True:
        if not getattr(harness, "_product_recovery", False) or run["state"]["phase"] in {"PLAN", "STEP_EXECUTE"}:
            run = run_step(
                harness,
                run,
                problem=problem,
                plan=plan,
                model_port=model_port,
                max_model_calls=max_model_calls,
                max_runtime_seconds=max_runtime_seconds,
            )
        run = verify_step(
            harness,
            run,
            problem=problem,
            verifier_port=verifier_port,
            max_model_calls=max_model_calls,
            max_runtime_seconds=max_runtime_seconds,
        )
        run = run_challenges(
            harness,
            run,
            problem=problem,
            model_port=model_port,
            verifier_port=verifier_port,
            max_rounds=max_rounds,
            max_model_calls=max_model_calls,
            max_runtime_seconds=max_runtime_seconds,
        )
        run = apply_traceback(harness, run)
        explore_guidance = run["state"].get("meta_guidance_decision")
        if (
            run["state"]["phase"] == "EXPLORE"
            and isinstance(explore_guidance, dict)
            and explore_guidance.get("action_type") == "explore_more"
            and transition_decision(run, run["state"], explore_guidance)
        ):
            run = _explore_after_guidance(
                harness, run, problem, model_port, max_model_calls, max_runtime_seconds
            )
        if (
            run["state"]["phase"] != "STEP_EXECUTE"
            or budget_reason(run["state"], {"max_model_calls": max_model_calls,
                                             "max_total_duration_seconds": max_runtime_seconds})
        ):
            return run
    return run


def _explore_after_guidance(harness, run, problem, model_port, max_model_calls, max_runtime_seconds):
    """Add one unverified Explore finding, then resume the current accepted-plan boundary."""
    from .explore import run_exploration

    round_number = len(run["state"].get("exploration_findings", [])) + 1
    run = run_exploration(
        harness,
        run,
        problem=problem,
        model_port=model_port,
        max_model_calls=max_model_calls,
        max_explore_rounds=round_number,
        max_runtime_seconds=max_runtime_seconds,
    )
    if run["state"]["phase"] == "TERMINAL":
        return run
    state = run["state"]
    guidance = state["meta_guidance_decision"]
    return harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={
            "event_id": f"meta-guidance-applied-{run['state_revision']}",
            "type": "meta_guidance_applied",
            "failure_type": guidance.get("failure_type"),
            "action_type": "explore_more",
            "specific_task_consumed": True,
            "role": "explore",
            **({"decision_revision": guidance["decided_at_revision"]}
               if isinstance(guidance.get("decided_at_revision"), int) else {}),
        },
        state_updates={
            "phase": "STEP_EXECUTE",
            "pending_guidance_task": None,
            "meta_guidance_decision": {**guidance, "consumed": {
                "event_type": "meta_guidance_applied",
                "state_revision": run["state_revision"] + 1,
                "role": "explore",
            }},
        },
    )
