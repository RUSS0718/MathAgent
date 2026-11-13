"""Strict step review and evidence persistence for supplied plans."""

import hashlib
from collections.abc import Mapping
from typing import Any

from .calls import CallInterrupted, latest_retry_id
from .explore import _HarnessOperations
from .review import VerifierPort


def normalize_verdict(reply: Any, current_index: int) -> dict[str, Any]:
    """Interpret exact structured enum values; never infer acceptance from prose."""
    reply = reply if isinstance(reply, Mapping) else {}
    goal = reply.get("goal_gate")
    logic = reply.get("logic_gate")
    verdict = reply.get("verdict")
    target = reply.get("trace_back_to")
    valid = (
        isinstance(goal, str)
        and goal in ("YES", "PARTIAL", "NO")
        and isinstance(logic, str)
        and logic in ("PASS", "FAIL", "UNCERTAIN")
        and isinstance(verdict, str)
        and verdict in ("ACCEPT", "CHALLENGE", "TRACE_BACK", "PROPOSE_REPLAN")
    )
    if verdict == "ACCEPT" and (goal != "YES" or logic != "PASS"):
        valid = False
    if verdict == "TRACE_BACK" and (
        isinstance(target, bool) or not isinstance(target, int) or not 1 <= target <= current_index
    ):
        valid = False
    return {
        "goal_gate": goal if isinstance(goal, str) else None,
        "logic_gate": logic if isinstance(logic, str) else None,
        "verdict": verdict if isinstance(verdict, str) else None,
        "trace_back_to": target
        if isinstance(target, int) and not isinstance(target, bool)
        else None,
        "valid": bool(valid),
    }


def _reject_contradictory_acceptance(verification: dict[str, Any]) -> dict[str, Any]:
    """Reject an ACCEPT verdict whose gates do not prove acceptance."""
    if (
        verification["verdict"] == "ACCEPT"
        and (verification["goal_gate"] != "YES" or verification["logic_gate"] != "PASS")
    ):
        verification.update(valid=False, reason="invalid_verifier_verdict")
    return verification


def verify_step(
    harness: _HarnessOperations,
    run: dict[str, Any],
    *,
    problem: str,
    verifier_port: VerifierPort | None,
    max_model_calls: int,
    max_runtime_seconds: int,
    round_number: int = 0,
) -> dict[str, Any]:
    """Review one report once, leaving later phases to their owning slices."""
    if verifier_port is None or run["state"]["phase"] != "STEP_VERIFY":
        return run
    run = harness.precheck_report(run)
    run = _run_guidance_for_failure(harness, run, max_model_calls, max_runtime_seconds)
    if run["state"]["phase"] != "STEP_VERIFY":
        return run
    from .budget import budget_reason, stop

    reason = budget_reason(run["state"], harness._config)
    if reason:
        return stop(harness, run, reason)
    state = run["state"]
    suffix = f"-challenge-{round_number}" if round_number else ""
    adoption_review = (state.get("serial_intervention") or {}).get("review_id")
    if adoption_review:
        suffix += f"-adoption-{adoption_review}"
    attempt = state["attempt_index"]
    suffix += f"-attempt-{attempt}" if attempt else ""
    step_id = state["current_step"]
    challenge_history = state["steps"].get(step_id, {}).get("challenge_history", [])
    if round_number == 0 and challenge_history:
        suffix += f"-challenge-continuation-{len(challenge_history)}"
    plan = state["plan"]
    index = next(i for i, step in enumerate(plan["steps"]) if step["step_id"] == step_id)
    step = plan["steps"][index]
    checkpoint_mode = harness._config.get("features", {}).get("reasoner_checkpoints") is True
    checkpoint = next(
        (
            item for item in reversed(state.get("reasoner_checkpoints", []))
            if item.get("checkpoint_id") == state["steps"].get(step_id, {}).get("checkpoint_id")
            and item.get("plan_version") == state["plan_version"]
            and item.get("step_id") == step_id
        ),
        None,
    ) if checkpoint_mode else None
    if checkpoint is not None:
        suffix += f"-checkpoint-{checkpoint['checkpoint_id']}"
    counters = dict(state["counters"])
    from .budget import budget_reason

    reason = budget_reason(state, {"max_model_calls": max_model_calls,
                                   "max_total_duration_seconds": max_runtime_seconds})
    if reason:
        return harness.commit_event(
            run["run_id"],
            expected_revision=run["state_revision"],
            event={
                "event_id": f"step-review-budget-{step_id}{suffix}",
                "type": "budget_exhausted",
                "reason": reason,
            },
            state_updates={
                "phase": "TERMINAL",
                "status": "partial_budget_exhausted",
                "budget": {**state.get("budget", {}), "exhaustion_reason": reason},
                "final_response": "Budget exhausted before step review; no verified answer is available.",
            },
        )
    counters["model_calls"] += 1
    from .counterexample import pending_review

    pending = pending_review(run) if getattr(harness, "_product_recovery", False) else None
    call_id = getattr(harness, "namespace_call_id", lambda value: value)(
        f"{run['run_id']}:step-verifier:{plan['version']}:{step_id}{suffix}"
    )
    adoption_receipt = adoption_review and call_id in state.get("calls", {})
    reserved = run if pending or adoption_receipt else harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={
            "event_id": f"step-review-dispatched-{step_id}{suffix}",
            "type": "step_review_dispatched",
            "step_id": step_id,
        },
        state_updates={"counters": counters},
    )
    report = state["steps"][step_id]["report"]
    request = {
        "run_id": run["run_id"],
        "call_id": call_id,
        "session_key": f"verify:{run['run_id']}:plan{plan['version']}:step{step_id}"
        + (f"-attempt-{attempt}" if attempt else ""),
        "round": round_number,
        "challenge_history": challenge_history,
        "role": "step_verifier",
        "problem": problem,
        "step": ({**step, "objective": checkpoint["objective"]}
                 if checkpoint is not None else step),
        **({"step_goal": step["objective"], "checkpoint": checkpoint}
           if checkpoint is not None else {}),
        "report": report,
        "current_step_index": index + 1,
        "state_revision": reserved["state_revision"],
    }

    if state.get('serial_intervention'):
        from .serial_intervention import applicable_results
        request['intervention_results'] = applicable_results(harness, run)

    def reserve_and_dispatch(current, seq, continuation_call_id, continuation_request,
                             *, purpose="compute"):
        nonlocal call_id
        # Claim-target repairs may continue an already answered computation.
        # Its call identity must own a distinct reservation event.
        identity = hashlib.sha256(continuation_call_id.encode()).hexdigest()[:16]
        event_suffix = f"{purpose}-{seq + 1}-{identity}"
        reserved = harness.commit_event(
            current["run_id"],
            expected_revision=current["state_revision"],
            event={
                "event_id": f"step-review-dispatched-{step_id}{suffix}-{event_suffix}",
                "type": "step_review_dispatched",
                "step_id": step_id,
                "role": "step_verifier",
            },
            state_updates={
                "counters": {
                    **current["state"]["counters"],
                    "model_calls": current["state"]["counters"]["model_calls"] + 1,
                },
            },
        )
        reply = harness.dispatch(reserved, verifier_port.verify, continuation_request)
        latest = harness.get_run(current["run_id"])
        call_id = latest_retry_id(latest["state"].get("calls", {}), continuation_call_id)
        return latest, reply

    try:
        if pending:
            call_id, reply = pending
        else:
            from . import protocol_repair

            try:
                reply = harness.dispatch(reserved, verifier_port.verify, request)
            except CallInterrupted as exc:
                reserved = protocol_repair.reserve_repair(
                    harness, run["run_id"], exc,
                    failure_event=lambda latest, failed: {
                        "event_id": f"step-review-parse-{step_id}{suffix}-{latest['state_revision']}",
                        "type": "step_review_parse_failed", "step_id": step_id,
                        "role": "step_verifier",
                        "summary": "Verifier reply failed the response protocol; one bounded repair follows",
                    },
                    dispatch_event={
                        "event_id": f"step-review-dispatched-{step_id}{suffix}-repair-1",
                        "type": "step_review_dispatched", "step_id": step_id,
                        "role": "step_verifier",
                    },
                )
                request = protocol_repair.repair_request(
                    request, failed_call=protocol_repair.interrupted_call(harness, run["run_id"], exc))
                call_id = request["call_id"]
                reply = harness.dispatch(reserved, verifier_port.verify, request)
    except CallInterrupted:
        latest = harness.get_run(run["run_id"])
        call = latest["state"].get("calls", {}).get(call_id, {})
        if call.get("error_category") not in {
            "invalid_role_schema", "invalid_json", "empty_response", "truncated_response"
        }:
            return latest
        failed_review = normalize_verdict(None, index + 1)
        failed_review.update(objection="", reason="invalid_verifier_response")
        return harness.commit_event(
            run["run_id"],
            expected_revision=latest["state_revision"],
            event={
                "event_id": f"step-review-invalid-{step_id}{suffix}",
                "type": "step_reviewed",
                "step_id": step_id,
                **failed_review,
                "summary": "Verifier response was invalid; the step was not accepted",
            },
            state_updates={
                "phase": "STEP_VERIFY",
                "status": "partial_aborted",
                "current_step": step_id,
                "steps": {
                    **latest["state"]["steps"],
                    step_id: {
                        **latest["state"]["steps"][step_id],
                        "status": "VERIFYING",
                        "verification": failed_review,
                    },
                },
            },
        )
    except Exception:
        reply = None
    from .verifier_compute import continue_review

    reserved, reply, unfulfilled = continue_review(
        harness,
        reserved,
        role="step_verifier",
        step_id=step_id,
        round_number=round_number,
        attempt_index=attempt,
        base_call_id=call_id,
        base_request=request,
        reply=reply,
        reserve_and_dispatch=reserve_and_dispatch,
    )
    verification = _reject_contradictory_acceptance(normalize_verdict(reply, index + 1))
    if unfulfilled:
        # A computation the reviewer asked for never completed; its verdict is not
        # an acceptance and must not promote any evidence.
        verification.update(valid=False, reason="verifier_tool_request_unfulfilled")
    if isinstance(reply, Mapping) and "answer_claim" in reply and not unfulfilled:
        from . import counterexample

        declared = counterexample.target(report, reply["answer_claim"])
        if declared is None:
            declaration = reply["answer_claim"]
            claims = report.get("claims", [])
            claim_index = declaration.get("claim_index") if isinstance(declaration, Mapping) else None
            repair_failure_reason = None
            if (type(claim_index) is int and isinstance(claims, list) and claims
                    and not 0 <= claim_index < len(claims)):
                from . import protocol_repair

                if protocol_repair.repair_enabled(harness._config):
                    target_request = protocol_repair.repair_request(
                        request,
                        instruction=(
                            "Your answer_claim used an index outside the current report. "
                            f"There are {len(claims)} claims, indexed from 0 through {len(claims) - 1}. "
                            "Re-evaluate the report and return the complete verifier response with "
                            "answer_claim bound to the exact existing claim. Keep all required fields "
                            "and gates faithful to the review; do not change them just to pass validation."
                        ),
                    )
                    target_call_id = target_request["call_id"]
                    target_request["retry_of"] = call_id
                    try:
                        reserved, reply = reserve_and_dispatch(
                            reserved, 0, target_call_id, target_request,
                            purpose="claim-target-repair",
                        )
                        call_id = target_call_id
                        reserved, reply, unfulfilled = continue_review(
                            harness,
                            reserved,
                            role="step_verifier",
                            step_id=step_id,
                            round_number=round_number,
                            attempt_index=attempt,
                            base_call_id=call_id,
                            base_request=target_request,
                            reply=reply,
                            reserve_and_dispatch=reserve_and_dispatch,
                        )
                    except CallInterrupted:
                        latest = harness.get_run(run["run_id"])
                        repair_call = latest["state"].get("calls", {}).get(target_call_id, {})
                        if repair_call.get("error_category") not in {
                            "invalid_role_schema", "invalid_json", "empty_response", "truncated_response"
                        }:
                            return latest
                        reply = None
                        repair_failure_reason = "invalid_verifier_response"
                    else:
                        verification = _reject_contradictory_acceptance(
                            normalize_verdict(reply, index + 1)
                        )
                        if unfulfilled:
                            verification.update(valid=False, reason="verifier_tool_request_unfulfilled")
                        declared = (
                            counterexample.target(report, reply.get("answer_claim"))
                            if isinstance(reply, Mapping) and "answer_claim" in reply and not unfulfilled
                            else None
                        )
            if declared is None:
                verification.update(
                    valid=False,
                    reason=("verifier_tool_request_unfulfilled" if unfulfilled
                            else repair_failure_reason or "invalid_answer_claim_target"),
                )
        if declared is not None and verification["valid"] and counterexample.missing_direction(declared):
            reserved = counterexample.run_check(
                harness, reserved, problem=problem, declared=declared, verifier_call_id=call_id,
            )
            if reserved["state"]["phase"] == "TERMINAL":
                return reserved
            result = counterexample.consumed_result(
                reserved["state"], step_id=step_id, verifier_call_id=call_id, declared=declared,
            )
            if result is None:
                verification.update(valid=False, reason="counterexample_check_not_completed")
            else:
                found = result["verdict"] == "FOUND_COUNTEREXAMPLE"
                verification.update(
                    verdict="CHALLENGE", goal_gate="PARTIAL",
                    logic_gate="FAIL" if found else "UNCERTAIN",
                    counterexample_verdict=result["verdict"],
                )
                reply = {**reply, "objection": (
                    f"Counterexample: {result['counterexample']}; {result['violated_conclusion']}"
                    if found else "No counterexample found within the reported scope; "
                                  "the missing proof direction remains a Conjecture."
                )}
    state = reserved["state"]
    checkpoint_status = state["steps"].get(step_id, {}).get("checkpoint_status")
    checkpoint_round = checkpoint.get("round") if checkpoint is not None else None
    verification["objection"] = (
        reply.get("objection", "")
        if isinstance(reply, Mapping) and isinstance(reply.get("objection", ""), str)
        else ""
    )
    if isinstance(reply, Mapping):
        if (
            isinstance(reply.get("reason"), str)
            and verification.get("reason") != "invalid_verifier_verdict"
        ):
            verification["reason"] = reply["reason"]
        directions = reply.get("forbidden_directions")
        if isinstance(directions, list) and all(isinstance(item, str) for item in directions):
            verification["forbidden_directions"] = directions
    # Classifications are the reviewer's explicit ruling under any verdict; the
    # controller verifies each declaration before anything reaches the ledger.
    # An unfulfilled or invalid review never promotes evidence.
    outcomes, rejections = [], []
    if verification["valid"] and not unfulfilled:
        from .classified import build_entries

        outcomes, rejections = build_entries(
            state, reply, step_id=step_id, report=report, review_call_id=call_id,
            suffix=suffix, plan_version=plan["version"], attempt_index=attempt,
        )
    obligation_evidence, obligation_rejections = [], []
    if (verification["valid"] and verification["verdict"] == "ACCEPT"
            and (not checkpoint_mode or checkpoint_status == "FINAL")
            and isinstance(state.get("problem_spec"), Mapping)):
        from .obligation_evidence import collect_obligation_evidence

        obligation_evidence, obligation_rejections = collect_obligation_evidence(
            state["problem_spec"],
            reply.get("obligation_evidence") if isinstance(reply, Mapping) else [],
            report=report,
            run_id=run["run_id"],
            review_call_id=call_id,
            state_revision=reserved["state_revision"],
            work_unit_id=step_id,
            work_unit_obligation_ids=step.get("obligation_ids", []),
            plan_version=plan["version"],
            attempt_index=attempt,
        )
    accepted = (
        verification["valid"]
        and verification["verdict"] == "ACCEPT"
        and (not checkpoint_mode or checkpoint_status == "FINAL")
    )
    combined_obligation_evidence = [
        *state.get("obligation_evidence_ledger", []), *obligation_evidence,
    ]
    next_ledger = state.get("obligation_ledger", [])
    checkpoint_accepted = (
        verification["valid"]
        and verification["verdict"] == "ACCEPT"
        and checkpoint_mode
        and checkpoint_status != "FINAL"
    )
    checkpoint_review = dict(verification) if checkpoint_accepted else None
    if checkpoint_accepted:
        verification = {
            **verification,
            "valid": False,
            "verdict": "CHECKPOINT_ACCEPTED",
        }
    phase = "STEP_VERIFY"
    current_step = step_id
    evidence = []
    if accepted:
        phase = "STEP_EXECUTE" if index + 1 < len(plan["steps"]) else "FINAL_GENERATE"
        current_step = (
            plan["steps"][index + 1]["step_id"] if index + 1 < len(plan["steps"]) else None
        )
        statements = [claim["statement"] for claim in report["claims"]]
        if not statements and report["argument"].strip():
            statements = [report["argument"]]
        evidence = [
            {
                "category": "step_result",
                "statement": statement,
                "source": step_id,
                "evidence_level": "llm_reviewed",
                "dependencies": step.get("depends_on", []),
            }
            for statement in statements
        ]
        if isinstance(state.get("problem_spec"), Mapping):
            from .obligation_evidence import (
                all_root_obligations_satisfied,
                update_obligation_ledger,
            )

            next_ledger = update_obligation_ledger(
                state["problem_spec"], state.get("obligation_ledger", []),
                combined_obligation_evidence,
            )
            if all_root_obligations_satisfied(next_ledger):
                phase = "FINAL_GENERATE"
                current_step = None
            elif index + 1 == len(plan["steps"]):
                phase = "TERMINAL"
                current_step = None
    elif checkpoint_accepted:
        phase = "STEP_EXECUTE"
        current_step = step_id
    elif verification["valid"]:
        phase = {
            "CHALLENGE": "CHALLENGE",
            "TRACE_BACK": "TRACE_BACK",
            "PROPOSE_REPLAN": "META_DECIDE",
        }[verification["verdict"]]
    from .handoff import enabled

    reviewed = (enabled(harness._config) and verification["valid"] and not checkpoint_accepted
                and verification["verdict"] in {"ACCEPT", "CHALLENGE"})
    if reviewed and not isinstance(state.get("problem_spec"), Mapping):
        phase = "STEP_EXECUTE" if index + 1 < len(plan["steps"]) else "FINAL_GENERATE"
        current_step = plan["steps"][index + 1]["step_id"] if index + 1 < len(plan["steps"]) else None
    if (accepted and isinstance(state.get("problem_spec"), Mapping)
            and phase == "TERMINAL"):
        current_step = None
    # The classified ledger is the single authoritative record: proven entries
    # reach final synthesis and rescue through its dependency-checked readers,
    # while Conjectures stay confined there and never become proven premises.
    from .classified import outcome_counts

    state_updates = {
        "phase": phase,
        "current_step": current_step,
        "steps": {
            **state["steps"],
            step_id: {
                **state["steps"][step_id],
                "status": "ACCEPTED" if accepted else "REVIEWED" if reviewed else "CHECKPOINT_ACCEPTED" if checkpoint_accepted else "VERIFYING",
                "verification": verification,
                **({"checkpoint_verification": checkpoint_review}
                   if checkpoint_review is not None else {}),
            },
        },
        "accepted_results": [*state["accepted_results"], *evidence],
        "verified_results_ledger": [
            *state.get("verified_results_ledger", []), *outcomes
        ],
    }
    if isinstance(state.get("problem_spec"), Mapping):
        state_updates["obligation_evidence_ledger"] = combined_obligation_evidence
        state_updates["obligation_ledger"] = next_ledger
        if obligation_rejections:
            state_updates["obligation_evidence_rejections"] = [
                *state.get("obligation_evidence_rejections", []), *obligation_rejections
            ]
        if phase == "TERMINAL" and accepted:
            state_updates.update(
                status="partial_aborted",
                result_reason="root_obligations_incomplete",
                final_response="Root obligations remain unverified; final synthesis was not admitted.",
            )
    if not verification["valid"] and not checkpoint_accepted:
        state_updates["status"] = "partial_aborted"
        if verification.get("reason") == "invalid_verifier_verdict":
            state_updates["result_reason"] = "invalid_verifier_verdict"
    event = {
        "event_id": f"step-reviewed-{step_id}{suffix}",
        "type": "step_reviewed",
        "step_id": step_id,
        **(checkpoint_review if checkpoint_review is not None else verification),
        **({"checkpoint_status": checkpoint_status} if checkpoint_status is not None else {}),
        **({"checkpoint_round": checkpoint_round} if checkpoint_round is not None else {}),
        **({"checkpoint_id": checkpoint["checkpoint_id"]} if checkpoint is not None else {}),
    }
    if outcomes:
        event["classified_outcomes"] = outcome_counts(outcomes)
    if rejections:
        event["rejected_outcomes"] = len(rejections)
    if obligation_evidence:
        event["obligation_evidence_count"] = len(obligation_evidence)
    if obligation_rejections:
        event["obligation_evidence_rejections"] = len(obligation_rejections)
    return harness.commit_event(
        run["run_id"],
        expected_revision=reserved["state_revision"],
        event=event,
        state_updates=state_updates,
    )


def _run_guidance_for_failure(harness, run, max_model_calls, max_runtime_seconds):
    if (
        harness._meta_port is None
        or harness._config.get("features", {}).get("meta_guidance") is not True
    ):
        return run
    state = run["state"]
    step_id = state.get("current_step")
    report = state.get("steps", {}).get(step_id, {}).get("report", {})
    report_receipts = set(report.get("tool_evidence_refs", []))
    failure_type = "stuck" if report.get("blocked") is True else None
    tool_failure = None
    for receipt in reversed(state.get("tool_receipts", [])):
        if receipt.get("step_id") != step_id or receipt.get("receipt_id") not in report_receipts:
            continue
        if receipt.get("source") != "docker_isolated" or receipt.get("unknown_outcome") is True:
            continue
        if receipt.get("executed") is True and receipt.get("cleanup_verified") is not True:
            continue
        status = receipt.get("status")
        if status == "timeout":
            failure_type, tool_failure = "timeout", "timeout"
        elif status in {"tool_error", "output_limit", "parse_error", "unavailable", "rejected"}:
            failure_type, tool_failure = "code_issue", (
                "output_mismatch" if status == "output_limit" else "execution_error"
            )
        elif status == "success" and receipt.get("comparison_status") == "mismatched":
            failure_type, tool_failure = "code_issue", "output_mismatch"
        if failure_type:
            break
    if failure_type is None:
        return run
    if any(
        item.get("kind") == "guidance"
        and item.get("plan_version") == state["plan_version"]
        and item.get("step_id") == step_id
        for item in state.get("meta_interventions", [])
    ):
        return run
    from .meta import run_meta

    return run_meta(
        harness,
        run,
        meta_port=harness._meta_port,
        metadata={
            "meta_guidance": {"failure_type": failure_type},
            **({"tool_failure": tool_failure} if tool_failure else {}),
        },
        max_model_calls=max_model_calls,
        max_runtime_seconds=max_runtime_seconds,
    )
