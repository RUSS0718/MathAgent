"""Single supplied-plan step execution and conservative report normalization."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .explore import ModelPort, _HarnessOperations
from .finalize import finish


def run_step(
    harness: _HarnessOperations,
    run: dict[str, Any],
    *,
    problem: str,
    plan: Mapping[str, Any],
    model_port: ModelPort,
    max_model_calls: int,
    max_runtime_seconds: int,
) -> dict[str, Any]:
    """Execute the first supplied step once, leaving the report pending review."""
    from .progress import guard_action

    run = guard_action(harness, run)
    if run["state"]["phase"] not in {"SETUP", "STEP_EXECUTE"}:
        return run
    state = run["state"]
    step = next(
        (item for item in plan["steps"] if item["step_id"] == state["current_step"]),
        plan["steps"][0],
    )
    step_id = step["step_id"]
    if isinstance(state.get("problem_spec"), Mapping):
        from .specification import prerequisites_satisfied

        work_unit = next(
            (item for item in state.get("work_units", [])
             if item.get("step_id", item.get("work_unit_id")) == step_id),
            None,
        )
        completed_work_units = {
            item["step_id"] for item in plan["steps"]
            if state.get("steps", {}).get(item["step_id"], {}).get("verification", {}).get("valid") is True
            and state["steps"][item["step_id"]]["verification"].get("verdict") == "ACCEPT"
        }
        completed_obligations = {
            obligation_id
            for item in state.get("obligation_ledger", [])
            if item.get("status") == "satisfied"
            for obligation_id in [item.get("obligation_id")]
        }
        if work_unit is None or not prerequisites_satisfied(
            work_unit, completed_work_units, completed_obligations
        ):
            return finish(harness, run, "partial_aborted", "work_unit_prerequisites_incomplete")
    from . import reasoner_checkpoint

    checkpoint_mode = reasoner_checkpoint.enabled(harness._config)
    current_checkpoints = reasoner_checkpoint.current_checkpoints(state) if checkpoint_mode else []
    parent_checkpoint = current_checkpoints[-1] if current_checkpoints else None
    if checkpoint_mode and len(current_checkpoints) >= reasoner_checkpoint.MAX_CHECKPOINT_ROUNDS:
        return finish(harness, run, "partial_aborted", "reasoner_checkpoint_round_limit")
    attempt = state["attempt_index"]
    previous = state["steps"].get(step_id, {})
    challenge_history = previous.get("challenge_history", [])
    suffix = f"-attempt-{attempt}" if attempt else ""
    if challenge_history:
        suffix += f"-challenge-continuation-{len(challenge_history)}"
    if checkpoint_mode and current_checkpoints:
        suffix += f"-checkpoint-{len(current_checkpoints) + 1}"
    session = f"reasoner:{run['run_id']}:plan{plan['version']}:attempt{attempt}"
    counters = dict(state["counters"])
    from .budget import budget_reason

    reason = budget_reason(state, {"max_model_calls": max_model_calls,
                                   "max_total_duration_seconds": max_runtime_seconds})
    if reason is not None:
        return harness.commit_event(
            run["run_id"],
            expected_revision=run["state_revision"],
            event={
                "event_id": "step-budget-exhausted",
                "type": "budget_exhausted",
                "reason": reason,
            },
            state_updates={
                "phase": "TERMINAL",
                "status": "partial_budget_exhausted",
                "budget": {**state.get("budget", {}), "exhaustion_reason": reason},
                "final_response": "Budget exhausted before step execution; no verified answer is available.",
            },
        )
    counters["model_calls"] += 1
    reserved = harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={
            "event_id": f"step-dispatched-{step_id}{suffix}",
            "type": "step_dispatched",
            "step_id": step_id,
        },
        state_updates={
            "phase": "STEP_EXECUTE",
            "plan": dict(plan),
            "plan_version": plan["version"],
            "current_step": step_id,
            "counters": counters,
        },
    )
    base_request = {
        "run_id": run["run_id"],
        "call_id": (
            f"{run['run_id']}:reasoner:checkpoint:{plan['version']}:{step_id}:"
            f"{len(current_checkpoints) + 1}{suffix}"
            if checkpoint_mode
            else f"{run['run_id']}:reasoner:{plan['version']}:{step_id}{suffix}"
        ),
        "session_key": session,
        "failure_records": state["failure_records"],
        "rescued_results": state.get("rescued_results", []),
        "role": "reasoner",
        "problem": problem,
        "step": dict(step),
        "state_revision": reserved["state_revision"],
        "tool_policy": {"allow": []},
    }
    request = base_request
    if checkpoint_mode:
        valid_sources = [
            deepcopy(item)
            for item in [*state.get("accepted_results", []), *state.get("verified_results_ledger", [])]
            if isinstance(item, Mapping)
            and item.get("invalidated") is not True
            and item.get("status") not in {"INVALIDATED", "invalidated"}
        ]
        request = reasoner_checkpoint.request(
            base_request,
            call_id=base_request["call_id"],
            round_number=len(current_checkpoints) + 1,
            parent=parent_checkpoint,
            objection=previous.get("verification", {}).get("objection"),
            guidance=state.get("meta_guidance_decision"),
        )
        request.update({
            "current_goal": step["objective"],
            "valid_sources": valid_sources,
            "open_obligations": list(parent_checkpoint.get("gaps", []))
            if parent_checkpoint else [],
        })
    guidance_task = state.get("pending_guidance_task")
    guidance = state.get("meta_guidance_decision")
    if isinstance(guidance_task, str) and guidance_task.strip():
        request["specific_task"] = guidance_task
    if challenge_history:
        request["challenge_history"] = challenge_history
        request["objection"] = previous.get("verification", {}).get("objection", "")
    from . import protocol_repair
    from .calls import CallInterrupted

    try:
        reply = harness.dispatch(
            reserved,
            model_port.complete,
            request,
        )
    except CallInterrupted as exc:
        reserved = protocol_repair.reserve_repair(
            harness, run["run_id"], exc,
            failure_event=lambda latest, failed: {
                "event_id": f"reasoner-parse-{step_id}{suffix}-{latest['state_revision']}",
                "type": "reasoner_parse_failed", "step_id": step_id, "role": "reasoner",
                "summary": "Reasoner reply failed the response protocol; one bounded repair follows",
            },
            dispatch_event={
                "event_id": f"step-dispatched-{step_id}{suffix}-repair-1",
                "type": "step_dispatched", "step_id": step_id, "role": "reasoner",
            },
        )
        reply = harness.dispatch(
            reserved,
            model_port.complete,
            protocol_repair.repair_request(
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
               for item in current_checkpoints):
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
    updates = {
        "phase": "STEP_VERIFY",
        "steps": {
            **state["steps"],
            step_id: {
                **previous,
                "status": "VERIFYING",
                "report": report,
                **({
                    "checkpoint_status": checkpoint["status"],
                    "checkpoint_id": checkpoint["checkpoint_id"],
                } if checkpoint is not None else {}),
            },
        },
    }
    if checkpoint is not None:
        checkpoint_record = reasoner_checkpoint.record(
            reserved,
            checkpoint,
            call_id=request["call_id"],
            checkpoint_round=len(current_checkpoints) + 1,
            plan_version=plan["version"],
            attempt_index=attempt,
            step_id=step_id,
            parent=parent_checkpoint,
        )
        updates["reasoner_checkpoints"] = [
            *state.get("reasoner_checkpoints", []), checkpoint_record
        ]
    action_type = guidance.get("action_type") if isinstance(guidance, Mapping) else None
    failure_type = next(
        (
            item.get("failure_type")
            for item in reversed(state.get("meta_interventions", []))
            if item.get("kind") == "guidance"
            and item.get("plan_version") == state["plan_version"]
            and item.get("step_id") == step_id
        ),
        None,
    )
    if request.get("specific_task"):
        updates["pending_guidance_task"] = None
    run = harness.commit_event(
        run["run_id"],
        expected_revision=reserved["state_revision"],
        event={
            "event_id": f"step-reported-{step_id}{suffix}",
            "type": "step_reported",
            "step_id": step_id,
            **({
                "checkpoint_id": checkpoint["checkpoint_id"],
                "checkpoint_status": checkpoint["status"],
                "checkpoint_round": len(current_checkpoints) + 1,
            } if checkpoint is not None else {}),
        },
        state_updates=updates,
    )
    if request.get("specific_task"):
        run = harness.commit_event(
            run["run_id"],
            expected_revision=run["state_revision"],
            event={
                "event_id": f"meta-guidance-applied-{run['state_revision']}",
                "type": "meta_guidance_applied",
                "step_id": step_id,
                "failure_type": failure_type,
                "action_type": action_type,
                "specific_task_consumed": True,
                **({"decision_revision": guidance["decided_at_revision"]}
                   if isinstance(guidance, Mapping)
                   and isinstance(guidance.get("decided_at_revision"), int) else {}),
            },
        )
    return run


def _normalize_report(reply: Any, step: Mapping[str, Any]) -> dict[str, Any]:
    reply = reply if isinstance(reply, Mapping) else {}
    claims = []
    values = reply.get("claims", [])
    for claim in values if isinstance(values, list) else []:
        if isinstance(claim, str):
            claim = {"statement": claim}
        if not isinstance(claim, Mapping) or not isinstance(claim.get("statement"), str):
            continue
        # Model-supplied refs never establish evidence; prechecks own receipts.
        label = claim.get("label")
        claims.append(
            {
                "statement": claim["statement"],
                "label": "easy-verify" if label == "easy-verify" else "hard-verify",
                "tool_evidence_refs": [],
            }
        )
        if label == "easy-verify" and isinstance(claim.get("tool_request"), Mapping):
            claims[-1]["tool_request"] = dict(claim["tool_request"])
    argument = reply.get("argument", "")
    candidate = reply.get("solution_candidate")
    extra = {}
    if isinstance(candidate, str):
        extra = {
            "solution_candidate": candidate,
            "answer_completeness": reply.get("answer_completeness", "partial"),
        }
    return {
        **extra,
        "step_id": step["step_id"],
        "objective": step["objective"],
        "argument": argument if isinstance(argument, str) else "",
        "claims": claims,
        "tool_evidence_refs": [],
        "blocked": reply.get("blocked") is True,
    }
