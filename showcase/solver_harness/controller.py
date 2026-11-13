"""Phase advancement for the explicit Solver Harness, independent of storage APIs."""

from collections.abc import Mapping
from typing import Any

from .challenge import run_plan
from .explore import run_exploration
from .finalize import run_finalization
from .harness_config import _non_negative_config_int, _positive_config_int
from .meta import run_meta
from .planning import generate_initial_plan
from .replan import run_replan
from .review import review_solution
from .traceback import apply_traceback


def run_supplied_plan_or_explore(
    harness,
    run: dict[str, Any],
    problem: str,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if run["state"].get("population_policy", {}).get("enabled") is True:
        plan = None if metadata is None else metadata.get("plan")
        if plan is not None:
            from .population_runtime import register_plans

            return register_plans(harness, run, plan)
        if run["state"]["phase"] == "SETUP":
            return harness.commit_event(
                run["run_id"], expected_revision=run["state_revision"],
                event={"event_id": "population-planning-requested", "type": "population_planning_requested"},
                state_updates={"phase": "PLAN"},
            )
        return run
    if harness._config.get("features", {}).get("star_routing") is True:
        from .star_routing import prepare_hint

        run = prepare_hint(harness, run, problem, metadata)
        if run["state"]["phase"] == "TERMINAL":
            return run
    plan = None if metadata is None else metadata.get("plan")
    if plan is None:
        return run_exploration_phase(harness, run, problem)
    if harness._model_port is None:
        return run
    return run_plan(
        harness,
        run,
        problem=problem,
        plan=plan,
        model_port=harness._model_port,
        verifier_port=harness._verifier_port,
        max_rounds=min(5, _positive_config_int(harness._config, "max_challenge_rounds", 5)),
        max_model_calls=_non_negative_config_int(harness._config, "max_model_calls", 2),
        max_runtime_seconds=_non_negative_config_int(
            harness._config, "max_total_duration_seconds", 3600
        ),
    )


def run_exploration_phase(harness, run: dict[str, Any], problem: str) -> dict[str, Any]:
    if harness._model_port is None:
        return run
    if harness._config.get("features", {}).get("star_routing") is True:
        from .star_routing import explore

        return explore(harness, run, problem)
    max_model_calls = _non_negative_config_int(harness._config, "max_model_calls", 2)
    max_explore_rounds = min(2, _positive_config_int(harness._config, "max_explore_rounds", 2))
    # STAR's 3600-second default bounds this Showcase run, not official scoring.
    explored = run_exploration(
        harness,
        run,
        problem=problem,
        model_port=harness._model_port,
        max_model_calls=max_model_calls,
        max_explore_rounds=max_explore_rounds,
        max_runtime_seconds=_non_negative_config_int(
            harness._config, "max_total_duration_seconds", 3600
        ),
    )

    if explored["state"]["phase"] == "EXPLORE_REVIEW":
        return review_solution(
            harness,
            explored,
            problem=problem,
            verifier_port=harness._verifier_port,
            max_model_calls=max_model_calls,
            max_runtime_seconds=_non_negative_config_int(
                harness._config, "max_total_duration_seconds", 3600
            ),
        )
    return explored


def advance(harness, run, metadata, problem):
    if run["state"].get("population_policy", {}).get("enabled") is True:
        from .population_lifecycle import advance_population

        return advance_population(harness, run, problem, metadata or {})
    run = run_meta(
        harness,
        run,
        meta_port=harness._meta_port,
        metadata=metadata or {},
        max_model_calls=_non_negative_config_int(harness._config, "max_model_calls", 2),
        max_runtime_seconds=_non_negative_config_int(
            harness._config, "max_total_duration_seconds", 3600
        ),
    )
    if harness._model_port is not None and run["state"]["phase"] == "TRACE_BACK":
        run = apply_traceback(harness, run)
    run = run_replan(
        harness, run, problem=problem, model_port=harness._model_port, config=harness._config
    )
    if harness._config.get("features", {}).get("serial_routes") is True:
        from .routes import sync_plan_route

        run = sync_plan_route(harness, run)
    if (
        harness._model_port is not None
        and run["state"]["phase"] == "STEP_EXECUTE"
        and run["state"].get("replan_count", 0)
    ):
        run = run_supplied_plan_or_explore(harness, run, problem, {"plan": run["state"]["plan"]})
    run = generate_initial_plan(
        harness,
        run,
        problem=problem,
        model_port=harness._model_port,
        config=harness._config,
        metadata=metadata or {},
    )
    if harness._config.get("features", {}).get("serial_routes") is True:
        from .routes import sync_plan_route

        run = sync_plan_route(harness, run)
    if (
        harness._model_port is not None
        and run["state"]["phase"] == "STEP_EXECUTE"
        and harness._config.get("features", {}).get("final_generation")
    ):
        run = run_supplied_plan_or_explore(harness, run, problem, {"plan": run["state"]["plan"]})
    return run_finalization(
        harness,
        run,
        problem=problem,
        model_port=harness._model_port,
        verifier_port=harness._verifier_port,
        config=harness._config,
    )


def protocol_failure_exit(harness, run, exc):
    """End dispatch honestly after an unrepaired known protocol failure.

    A fully received response that cannot satisfy the response protocol is a
    known failure, never an unknown remote outcome: bounded repair either
    already happened or has no owner here, so no further action is dispatched
    and the original Run, ledger and deadline stay untouched.
    """
    from .calls import CallInterrupted

    if not isinstance(exc, CallInterrupted):
        return None
    call = run["state"].get("calls", {}).get(getattr(exc, "call_id", None))
    if (call is not None and call.get("status") == "policy_rejected"
            and run["state"]["phase"] != "TERMINAL"):
        category = call.get("error_category") or "policy_rejected"
        is_context = category.startswith("context_")
        decision = call.get("transport_decision") or call.get("transport") or {}
        return harness.commit_event(
            run["run_id"],
            expected_revision=run["state_revision"],
            event={
                "event_id": f"{category}-terminal-{run['state_revision']}",
                "type": "context_capacity_terminal" if is_context else "transport_policy_rejected",
                "error_category": category,
                "transport": decision.get("transport"),
                "transport_reason": decision.get("reason"),
                "transport_evidence_kind": decision.get("evidence_kind"),
                "new_run_required": decision.get("new_run_required") is True,
                "summary": ("Run terminated after context capacity rejected this call"
                            if is_context else
                            "Transport policy rejected this call before provider dispatch"),
            },
            state_updates={
                "phase": "TERMINAL",
                "status": "partial_aborted",
                "result_reason": category,
                "final_response": (
                    "This call was rejected before provider dispatch. Previously committed results "
                    "and evidence are preserved. context_capacity_exceeded: split the task into smaller parts while "
                    "retaining the original problem and relevant evidence."
                    if category == "context_capacity_exceeded" else
                    f"This call was rejected before provider dispatch. Previously committed results "
                    f"and evidence are "
                    f"preserved. Context policy rejected dispatch ({category}); verify the frozen "
                    "provider profile or split the task while retaining the original requirements."
                    if is_context else
                    "No verified answer is available: the Run transport policy requires a new Run."
                ),
            },
        )
    if call is None or call.get("status") != "protocol_failed" or run["state"]["phase"] == "TERMINAL":
        return None
    return harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={
            "event_id": f"protocol-failure-terminal-{run['state_revision']}",
            "type": "protocol_failure_unrepaired",
            "role": call.get("role"),
            "error_category": call.get("error_category"),
            "summary": "Complete response failed the response protocol; bounded recovery did not continue",
        },
        state_updates={
            "phase": "TERMINAL",
            "status": "partial_aborted",
            "result_reason": "protocol_failure_unrepaired",
            "final_response": "No verified answer is available: the model response failed the response protocol.",
        },
    )


def advance_product(harness, run, problem):
    """Continue the existing phases under S3; never replay an interrupted action."""
    from ..run_control import check_control

    for _ in range(64):
        if run["state"].get("clarification", {}).get("status") == "waiting":
            return run
        if run["state"]["phase"] == "TERMINAL" or run["state"]["status"] in {
            "interrupted", "recovered_pending_validation"
        }:
            return run
        check_control()
        revision = run["state_revision"]
        from .budget import HardBudgetStop
        from .calls import CallInterrupted

        try:
            run = advance(harness, run, {}, problem)
        except (HardBudgetStop, CallInterrupted) as exc:
            latest = harness.get_run(run["run_id"])
            terminated = protocol_failure_exit(harness, latest, exc)
            return latest if terminated is None else terminated
        if run["state_revision"] == revision:
            return run
    return run  # Explicitly incomplete; bridge never calls this a reviewed success.
