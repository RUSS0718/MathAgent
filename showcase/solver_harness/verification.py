"""Strict step review and evidence persistence for supplied plans."""

from collections.abc import Mapping
from typing import Any

from .calls import CallInterrupted
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
    attempt = state["attempt_index"]
    suffix += f"-attempt-{attempt}" if attempt else ""
    step_id = state["current_step"]
    challenge_history = state["steps"].get(step_id, {}).get("challenge_history", [])
    if round_number == 0 and challenge_history:
        suffix += f"-challenge-continuation-{len(challenge_history)}"
    plan = state["plan"]
    index = next(i for i, step in enumerate(plan["steps"]) if step["step_id"] == step_id)
    step = plan["steps"][index]
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
    reserved = harness.commit_event(
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
    call_id = f"{run['run_id']}:step-verifier:{plan['version']}:{step_id}{suffix}"
    try:
        reply = harness.dispatch(
            reserved,
            verifier_port.verify,
            {
                "run_id": run["run_id"],
                "call_id": call_id,
                "session_key": f"verify:{run['run_id']}:plan{plan['version']}:step{step_id}"
                + (f"-attempt-{attempt}" if attempt else ""),
                "round": round_number,
                "challenge_history": challenge_history,
                "role": "step_verifier",
                "problem": problem,
                "step": step,
                "report": report,
                "current_step_index": index + 1,
                "state_revision": reserved["state_revision"],
            },
        )
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
    verification = normalize_verdict(reply, index + 1)
    if isinstance(reply, Mapping) and "answer_claim" in reply:
        from . import counterexample

        declared = counterexample.target(report, reply["answer_claim"])
        if declared is None:
            verification.update(valid=False, reason="invalid_answer_claim_target")
        elif not declared["both_directions_proved"]:
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
    verification["objection"] = (
        reply.get("objection", "")
        if isinstance(reply, Mapping) and isinstance(reply.get("objection", ""), str)
        else ""
    )
    if isinstance(reply, Mapping):
        if isinstance(reply.get("reason"), str):
            verification["reason"] = reply["reason"]
        directions = reply.get("forbidden_directions")
        if isinstance(directions, list) and all(isinstance(item, str) for item in directions):
            verification["forbidden_directions"] = directions
    accepted = verification["valid"] and verification["verdict"] == "ACCEPT"
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
    elif verification["valid"]:
        phase = {
            "CHALLENGE": "CHALLENGE",
            "TRACE_BACK": "TRACE_BACK",
            "PROPOSE_REPLAN": "META_DECIDE",
        }[verification["verdict"]]
    state_updates = {
        "phase": phase,
        "current_step": current_step,
        "steps": {
            **state["steps"],
            step_id: {
                **state["steps"][step_id],
                "status": "ACCEPTED" if accepted else "VERIFYING",
                "verification": verification,
            },
        },
        "accepted_results": [*state["accepted_results"], *evidence],
    }
    if not verification["valid"]:
        state_updates["status"] = "partial_aborted"
    return harness.commit_event(
        run["run_id"],
        expected_revision=reserved["state_revision"],
        event={
            "event_id": f"step-reviewed-{step_id}{suffix}",
            "type": "step_reviewed",
            "step_id": step_id,
            **verification,
        },
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
        elif status == "success" and receipt.get("assertion_matched") is False:
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
