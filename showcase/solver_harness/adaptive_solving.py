"""Optional candidate-first routing over existing Explore and review contracts."""

from .explore import run_exploration
from .finalize import commit
from .review import review_solution

VERSION = "adaptive-solving-v1"


def search_context(state):
    """Fingerprint declared scope and actual feedback, never timing or renamed steps.

    This is a search-state identity, not a claim that natural-language goals are
    mathematically equivalent. Tool feedback permits reconsideration, not proof gain.
    """
    import hashlib
    import json

    from .finalize import valid_facts

    evidence = {
        "specification": state.get("problem_spec"),
        "verified_results": [
            {key: record.get(key) for key in ("category", "statement", "scope", "evidence_level")}
            for record in valid_facts(state)],
        "confirmed_failures": [
            {key: record.get(key) for key in ("kind", "reason", "forbidden_directions")}
            for record in state.get("confirmed_failures_ledger", [])],
        "tool_feedback": [
            {key: receipt.get(key) for key in (
                "tool", "input", "status", "executed", "output", "assertion_matched", "comparison_status")}
            for receipt in state.get("tool_receipts", []) if receipt.get("executed") is True],
        "formal_environment": (state.get("formal_verification") or {}).get("environment"),
    }
    # Identical repeated feedback is not a new search state.
    for key in ("tool_feedback", "verified_results", "confirmed_failures"):
        evidence[key] = sorted({json.dumps(item, sort_keys=True, ensure_ascii=False)
                                for item in evidence[key]})
    return hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def explore_direct(harness, run, problem):
    """Try a complete candidate and at most one feedback-directed correction."""
    config = harness._config
    from .dependency_routing import planning_requirement, require_plan

    run = require_plan(harness, run)
    if run["state"]["phase"] == "PLAN" and planning_requirement(run["state"]):
        return run
    policy = run["state"].get("adaptive_solving")
    if policy is None:
        run = commit(harness, run, "adaptive_solving_started", {
            "adaptive_solving": {"version": VERSION, "corrections": 0,
                                 "reason": "candidate_first"}}, reason="candidate_first")
    while True:
        run = require_plan(harness, run)
        if run["state"]["phase"] == "PLAN" and planning_requirement(run["state"]):
            return run
        if (run["state"]["phase"] == "PLAN" and
                len(run["state"].get("whole_solution_reviews", [])) >
                run["state"]["adaptive_solving"].get("processed_reviews", 0)):
            run = _after_review(harness, run)
            if run["state"]["phase"] == "PLAN":
                return run
        if run["state"]["phase"] != "EXPLORE_REVIEW":
            run = run_exploration(
                harness, run, problem=problem, model_port=harness._model_port,
                max_model_calls=config.get("max_model_calls", 2),
                max_explore_rounds=len(run["state"].get("exploration_findings", [])) + 1,
                max_runtime_seconds=config.get("max_total_duration_seconds", 3600))
        if run["state"]["phase"] == "TERMINAL":
            return run
        if run["state"]["phase"] != "EXPLORE_REVIEW":
            return _route(harness, run, "complete_candidate_unavailable")
        run = review_solution(
            harness, run, problem=problem, verifier_port=harness._verifier_port,
            max_model_calls=config.get("max_model_calls", 2),
            max_runtime_seconds=config.get("max_total_duration_seconds", 3600))
        if run["state"]["phase"] == "TERMINAL":
            return run
        run = _after_review(harness, run)
        if run["state"]["phase"] == "PLAN":
            return run


def _after_review(harness, run):
    """Consume one persisted rejection once, including the post-review crash window."""
    policy = {**run["state"]["adaptive_solving"],
              "processed_reviews": len(run["state"].get("whole_solution_reviews", []))}
    feedback = run["state"].get("candidate_review_feedback", {})
    concrete = any(isinstance(feedback.get(key), str) and feedback[key].strip()
                   for key in ("reason", "counterexample"))
    if (policy["corrections"] >= 1 or not concrete
            or feedback.get("runtime_failure") is True):
        return _route(harness, run, "whole_review_requires_planning", policy=policy)
    return commit(harness, run, "adaptive_candidate_correction", {
        "phase": "EXPLORE", "adaptive_solving": {
            **policy, "corrections": 1, "reason": "concrete_review_objection"}},
        reason="concrete_review_objection")


def _route(harness, run, reason, *, policy=None):
    """Record an upgrade without changing identity, deadline or root resources."""
    return commit(harness, run, "adaptive_planning_required", {
        "phase": "PLAN", "adaptive_solving": {
            **(policy or run["state"]["adaptive_solving"]), "reason": reason}}, reason=reason)
