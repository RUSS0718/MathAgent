"""Explicit v1.2 Explore polish, partial routing and preplan hints."""

from .budget import budget_reason, stop
from .explore import run_exploration
from .finalize import commit, dispatch, finish
from .review import review_solution

MAX_HINT_CHARS = 2000


def is_valid_hint(hint):
    """Return whether a hint is nonblank text within the shared size bound."""
    return isinstance(hint, str) and bool(hint.strip()) and len(hint) <= MAX_HINT_CHARS


def prepare_hint(harness, run, problem, metadata):
    if run["state"].get("hint_prepared"):
        return run
    mode = harness._config.get("hint_mode", "none")
    if mode not in {"none", "meta_auto", "user_hint"}:
        raise ValueError("invalid_hint_mode")
    hint = None
    if mode == "user_hint":
        hint = (metadata or {}).get("user_hint")
        if not is_valid_hint(hint):
            raise ValueError("user_hint_required")
    elif mode == "meta_auto":
        reason = budget_reason(run["state"], harness._config)
        if reason:
            return stop(harness, run, reason)
        if harness._meta_port is None:
            return finish(harness, run, "partial_aborted", "hint_meta_unavailable")
        run, reply = dispatch(
            harness,
            run,
            harness._meta_port.complete,
            {
                "role": "meta",
                "action": "preplan_hint",
                "problem": problem,
                "instruction": "Return a concise strategic hint, not a completed proof, as {hint: string}.",
            },
        )
        hint = reply.get("hint") if isinstance(reply, dict) else None
        if not is_valid_hint(hint):
            return finish(harness, run, "partial_aborted", "invalid_preplan_hint")
    return commit(
        harness,
        run,
        "hint_prepared",
        {"hint_prepared": True, "hint_mode": mode, "preplan_hint": hint},
    )


def explore(harness, run, problem):
    config = harness._config
    limit = min(2, config.get("max_explore_rounds", 2))
    for number in range(1, limit + 1):
        run = run_exploration(
            harness,
            run,
            problem=problem,
            model_port=harness._model_port,
            max_model_calls=config.get("max_model_calls", 2),
            max_explore_rounds=number,
            max_runtime_seconds=config.get("max_total_duration_seconds", 3600),
        )
        if run["state"]["phase"] == "TERMINAL":
            return run
        finding = run["state"]["exploration_findings"][-1]
        if finding["assessment"] == "SOLVED":
            reason = budget_reason(run["state"], config)
            if reason:
                return stop(harness, run, reason)
            session = f"explore:{run['run_id']}:{number}"
            run, reply = dispatch(
                harness,
                run,
                harness._model_port.complete,
                {
                    "role": "explore_polish",
                    "round": number,
                    "session_key": session,
                    "problem": problem,
                    "solution_candidate": finding.get("solution_candidate", ""),
                    "instruction": "Polish the complete candidate; return solution_candidate. Do not add unsupported facts.",
                },
            )
            candidate = reply.get("solution_candidate") if isinstance(reply, dict) else None
            if not isinstance(candidate, str) or not candidate.strip():
                return finish(harness, run, "partial_aborted", "PARSE_ERROR")
            findings = [
                *run["state"]["exploration_findings"][:-1],
                {**finding, "solution_candidate": candidate,
                 "original_solution_candidate": finding.get("solution_candidate", "")},
            ]
            run = commit(harness, run, "exploration_polished", {"exploration_findings": findings})
            return review_solution(
                harness,
                run,
                problem=problem,
                verifier_port=harness._verifier_port,
                max_model_calls=config.get("max_model_calls", 2),
                max_runtime_seconds=config.get("max_total_duration_seconds", 3600),
            )
        if finding["assessment"] != "PARTIALLY_SOLVED" or number >= limit:
            return run
        reason = budget_reason(run["state"], config)
        if reason:
            return stop(harness, run, reason)
        if harness._meta_port is None:
            return finish(harness, run, "partial_aborted", "partial_meta_unavailable")
        run, decision = dispatch(
            harness,
            run,
            harness._meta_port.complete,
            {
                "role": "meta",
                "action": "partial_exploration",
                "problem": problem,
                "findings": run["state"]["exploration_findings"],
                "instruction": "Choose RETRY or PLAN with reason; do not take over the proof.",
            },
        )
        if (
            not isinstance(decision, dict)
            or decision.get("decision") not in {"RETRY", "PLAN"}
            or not isinstance(decision.get("reason"), str)
        ):
            return finish(harness, run, "partial_aborted", "invalid_partial_meta_decision")
        run = commit(
            harness,
            run,
            "partial_exploration_routed",
            {"phase": "EXPLORE" if decision["decision"] == "RETRY" else "PLAN"},
            decision=decision,
        )
        if decision["decision"] == "PLAN":
            return run
    return run
