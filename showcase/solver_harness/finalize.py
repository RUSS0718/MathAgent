"""Opt-in final synthesis and bounded independent whole-solution review."""

from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime

from ..redaction import redact


def commit(harness, run, kind, updates, **details):
    return harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={"event_id": f"{kind}-{run['state_revision']}", "type": kind, **details},
        state_updates=updates,
    )


def budget_reason(state, config):
    elapsed = (datetime.now(UTC) - datetime.fromisoformat(state["created_at"])).total_seconds()
    if elapsed >= config.get("max_total_duration_seconds", 3600):
        return "runtime_budget_exhausted"
    if state["counters"]["model_calls"] >= config.get("max_model_calls", 2):
        return "model_call_budget_exhausted"
    return None


def finish(harness, run, status, reason, candidate=""):
    updates = {
        "phase": "TERMINAL",
        "status": status,
        "finalization_reason": reason,
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
    request = harness.prepare_request(
        run,
        {
            "run_id": run["run_id"],
            "call_id": f"{run['run_id']}:{request['role']}:{run['state_revision']}",
            "allowed_tools": [],
            "tool_policy": {"allow": []},
            **request,
        },
    )
    request.update(allowed_tools=[], tool_policy={"allow": []})
    try:
        if hasattr(harness, "dispatch"):
            reply = harness.dispatch(run, operation, request)
        else:
            reply = operation(deepcopy(request))
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
    known = set(accepted_steps)
    pending = deepcopy(state.get("accepted_results", []))
    facts = []
    while pending:
        selected = []
        for fact in pending:
            dependencies = fact.get("dependencies")
            if (
                not fact.get("invalidated")
                and fact.get("evidence_level") in {"llm_reviewed", "tool_verified"}
                and isinstance(fact.get("statement"), str)
                and fact["statement"].strip()
                and isinstance(dependencies, list)
                and all(d in known for d in dependencies)
                and (fact.get("source") in accepted_steps or fact.get("result_id"))
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
    previous_review = None
    facts = valid_facts(state)
    for number in range(retries + 1):
        reason = budget_reason(run["state"], config)
        if reason:
            return finish(harness, run, "partial_budget_exhausted", reason)
        if model_port is None:
            return finish(harness, run, "partial_aborted", "final_generator_unavailable")
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
        run, review = dispatch(
            harness,
            run,
            verifier_port.verify,
            {
                "role": "whole_solution_verifier",
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
            },
        )
        valid = isinstance(review, Mapping) and review.get("verdict") in {"ACCEPT", "REJECT"}
        attempt["review"] = (
            review
            if valid
            else {"verdict": "UNAVAILABLE", "reason": "invalid_or_failed_final_review"}
        )
        run = commit(
            harness,
            run,
            "final_candidate_reviewed",
            {"final_solution_attempts": attempts},
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
