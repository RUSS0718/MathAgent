"""Opt-in final synthesis and bounded independent whole-solution review."""

from collections.abc import Mapping
from copy import deepcopy

from ..redaction import redact
from .budget import budget_reason
from .final_binding import review_record


def commit(harness, run, kind, updates, **details):
    return harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={"event_id": f"{kind}-{run['state_revision']}", "type": kind, **details},
        state_updates=updates,
    )


def finish(harness, run, status, reason, candidate=""):
    updates = {
        "phase": "TERMINAL",
        "status": status,
        "result_reason": reason,
        "final_response": candidate or f"No verified final answer is available: {reason}.",
    }
    if "budget_exhausted" in reason:
        updates["budget"] = {**run["state"].get("budget", {}), "exhaustion_reason": reason}
    return commit(harness, run, "finalization_completed", updates, reason=reason)


def dispatch(harness, run, operation, request):
    state = run["state"]
    run = commit(
        harness,
        run,
        "finalization_dispatched",
        {"counters": {**state["counters"], "model_calls": state["counters"]["model_calls"] + 1}},
        role=request["role"],
    )
    request = {
        "run_id": run["run_id"],
        "call_id": f"{run['run_id']}:{request['role']}:{run['state_revision']}",
        "allowed_tools": [],
        "tool_policy": {"allow": []},
        **request,
    }
    if request["role"] in {"final_generator", "whole_solution_verifier"}:
        request["finalization_scope"] = True

    def invoke(prepared):
        if request["role"] == "final_generator":
            prepared = deepcopy(prepared)
            prepared.update(allowed_tools=[], tool_policy={"allow": []})
        return operation(prepared)

    try:
        reply = harness.dispatch(run, invoke, request)
        return run, redact(deepcopy(dict(reply)))
    except Exception:
        return run, None


def valid_facts(state):
    """Exclude invalidated, unsupported, missing or cyclic dependent records."""
    plan = state.get("plan", {})
    steps = state.get("steps", {})
    accepted_steps = {
        step["step_id"]
        for step in plan.get("steps", [])
        if steps.get(step["step_id"], {}).get("verification", {}).get("valid") is True
        and steps[step["step_id"]]["verification"].get("verdict") == "ACCEPT"
    }
    invalid_ids = {
        result.get("result_id")
        for failure in state.get("failure_records", [])
        for result in failure.get("invalidated_results", [])
        if result.get("result_id")
    }
    known = set(accepted_steps)
    pending = deepcopy(state.get("accepted_results", []))
    facts = []
    while pending:
        selected = []
        for fact in pending:
            dependencies = fact.get("dependencies")
            if (
                not fact.get("invalidated")
                and fact.get("valid", True)
                and fact.get("status") not in {"INVALIDATED", "invalidated"}
                and fact.get("result_id") not in invalid_ids
                and fact.get("evidence_level") in {"llm_reviewed", "tool_verified"}
                and isinstance(fact.get("statement"), str)
                and fact["statement"].strip()
                and isinstance(dependencies, list)
                and all(d in known for d in dependencies)
                and (fact.get("source") in accepted_steps or fact.get("result_id")
                     or fact in state.get("rescued_results", []))
            ):
                facts.append(fact)
                if fact.get("result_id"):
                    known.add(fact["result_id"])
                selected.append(fact)
        if not selected:
            break
        pending = [fact for fact in pending if fact not in selected]
    return facts


def run_finalization(harness, run, *, problem, model_port, verifier_port, config):
    features = config.get("features", {})
    if not features.get("final_generation") or run["state"]["phase"] != "FINAL_GENERATE":
        return run
    state = run["state"]
    plan_steps = state.get("plan", {}).get("steps", [])
    if not plan_steps or any(
        state["steps"].get(step["step_id"], {}).get("verification", {}).get("verdict") != "ACCEPT"
        or state["steps"].get(step["step_id"], {}).get("verification", {}).get("valid") is not True
        for step in plan_steps
    ):
        return finish(harness, run, "partial_aborted", "unaccepted_plan_steps")
    retries = config.get("max_final_solution_retries", 2)
    if isinstance(retries, bool) or not isinstance(retries, int) or not 0 <= retries <= 20:
        raise ValueError("config.max_final_solution_retries must be 0..20")
    attempts = deepcopy(state.get("final_solution_attempts", []))
    current_attempts = [attempt for attempt in attempts
                        if attempt["plan_version"] == state["plan_version"]
                        and attempt["attempt_index"] == state["attempt_index"]]
    previous_review = current_attempts[-1].get("review") if current_attempts else None
    pending_review = (getattr(harness, "_product_recovery", False)
                      and current_attempts and current_attempts[-1].get("review") is None)
    # Reviewing the existing candidate spends no new candidate-generation slot.
    remaining = retries + 1 - len(current_attempts) + int(bool(pending_review))
    facts = valid_facts(state)
    for _ in range(max(0, remaining)):
        reason = budget_reason(run["state"], config)
        if reason:
            return finish(harness, run, "partial_budget_exhausted", reason)
        if model_port is None:
            return finish(harness, run, "partial_aborted", "final_generator_unavailable")
        pending_review = (getattr(harness, "_product_recovery", False)
                          and current_attempts and current_attempts[-1].get("review") is None)
        if pending_review:
            attempt = current_attempts[-1]
            candidate = attempt["candidate"]
            session = attempt["session_key"]
        else:
            session = f"final:{run['run_id']}:plan{state['plan_version']}:attempt{state['attempt_index']}:candidate{len(attempts)}"
            run, reply = dispatch(
                harness,
                run,
                model_port.complete,
                {
                    "role": "final_generator",
                    "session_key": session,
                    "problem": problem,
                    "accepted_results": facts,
                    "previous_review": previous_review,
                    "instruction": "Synthesize a complete answer to the original problem from only the accepted facts. Return final_response.",
                },
            )
            candidate = reply.get("final_response") if isinstance(reply, Mapping) else None
            if not isinstance(candidate, str) or not candidate.strip():
                return finish(harness, run, "partial_aborted", "invalid_final_candidate")
            attempt = {
                "attempt": len(attempts),
                "plan_version": state["plan_version"],
                "attempt_index": state["attempt_index"],
                "candidate": candidate,
                "accepted_results": facts,
                "review": None,
                "session_key": session,
            }
            attempts.append(attempt)
            current_attempts.append(attempt)
            run = commit(
                harness,
                run,
                "final_candidate_generated",
                {"final_solution_attempts": attempts, "phase": "FINAL_GENERATE"},
            )
        if not features.get("final_solution_review") or verifier_port is None:
            reason = (
                "final_review_disabled"
                if not features.get("final_solution_review")
                else "final_verifier_unavailable"
            )
            return finish(harness, run, "completed_unverified", reason, candidate)
        reason = budget_reason(run["state"], config)
        if reason:
            return finish(harness, run, "partial_budget_exhausted", reason, candidate)
        base_request = {
            "role": "whole_solution_verifier",
            "call_id": f"whole-review:{session}",
            "session_key": f"whole_verify:{session}",
            "problem": problem,
            "solution_candidate": candidate,
            "accepted_results": facts,
            "review_criteria": [
                "original_problem_consistency",
                "completeness",
                "cross_step_logic",
                "output_format",
            ],
        }
        run, review = dispatch(harness, run, verifier_port.verify, base_request)
        from .verifier_compute import continue_review, declared_request

        if isinstance(review, Mapping) and declared_request(review) is not None:

            def reserve_and_dispatch(current, _seq, _call_id, continuation):
                return dispatch(harness, current, verifier_port.verify, continuation)

            run, review, unfulfilled = continue_review(
                harness,
                run,
                role="whole_solution_verifier",
                step_id=None,
                round_number=0,
                attempt_index=state["attempt_index"],
                base_call_id=f"whole-review:{session}",
                base_request=base_request,
                reply=review,
                reserve_and_dispatch=reserve_and_dispatch,
            )
            if unfulfilled:
                review = {
                    "verdict": "UNAVAILABLE",
                    "reason": "verifier_tool_request_unfulfilled",
                }
        valid = (
            isinstance(review, Mapping)
            and isinstance(review.get("verdict"), str)
            and review["verdict"] in {"ACCEPT", "REJECT"}
        )
        attempt["review"] = (
            review
            if valid
            else {"verdict": "UNAVAILABLE", "reason": "invalid_or_failed_final_review"}
        )
        run = commit(
            harness,
            run,
            "final_candidate_reviewed",
            {"final_solution_attempts": attempts,
             "whole_solution_reviews": [*run["state"].get("whole_solution_reviews", []),
                 review_record(run, candidate, attempt["review"]["verdict"],
                     call_id=f"whole-review:{session}",
                     origin="final_generator", facts=facts)]},
            review=attempt["review"],
        )
        if not valid:
            return finish(harness, run, "completed_unverified", "final_verifier_failed", candidate)
        if review["verdict"] == "ACCEPT":
            return finish(
                harness, run, "completed_llm_reviewed", "final_verifier_accepted", candidate
            )
        previous_review = review
    return finish(harness, run, "partial_aborted", "final_review_retries_exhausted")
