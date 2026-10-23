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
    if (
        harness._model_port is not None
        and run["state"]["phase"] == "STEP_EXECUTE"
        and run["state"].get("replan_count", 0)
    ):
        run = run_supplied_plan_or_explore(harness, run, problem, {"plan": run["state"]["plan"]})
    run = generate_initial_plan(
        harness, run, problem=problem, model_port=harness._model_port, config=harness._config
    )
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


def advance_product(harness, run, problem):
    """Continue the existing phases under S3; never replay an interrupted action."""
    from ..run_control import check_control

    for _ in range(64):
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
        except (HardBudgetStop, CallInterrupted):
            return harness.get_run(run["run_id"])
        if run["state_revision"] == revision:
            return run
    return run  # Explicitly incomplete; bridge never calls this a reviewed success.
