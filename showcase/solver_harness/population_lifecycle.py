"""Owner, recovery and final delivery boundaries for the concurrent policy."""

import math
from copy import deepcopy

from .harness_config import SolverValidationError


def validate_config(config):
    """Require existing engineering producers and a frozen, explicit new policy."""
    features = config.get("features", {})
    if any(features.get(key) is not True for key in (
        "problem_spec", "proof_graph", "progress_scheduling", "stream_recovery",
        "final_generation", "final_solution_review",
    )) or features.get("serial_routes") is True:
        raise SolverValidationError("population_prerequisites_required")
    policy = config.get("population_policy", {})
    if (policy.get("enabled") is not True
            or policy.get("version") != "concurrent-aprs-v1"
            or policy.get("schema_version") != "population-v1"):
        raise SolverValidationError("population_policy_invalid")
    capacity = policy.get("capacity", {})
    if (not isinstance(capacity, dict)
            or capacity.get("status") not in {"controlled", "verified"}
            or type(capacity.get("max_inflight")) is not int or capacity["max_inflight"] < 1
            or type(capacity.get("worker_slots")) is not int
            or capacity["worker_slots"] < capacity["max_inflight"]
            or not isinstance(capacity.get("service_id"), str) or not capacity["service_id"].strip()
            or not isinstance(capacity.get("evidence_ref"), str) or not capacity["evidence_ref"].strip()):
        raise SolverValidationError("population_capacity_unverified")
    timeout = policy.get("request_timeout_seconds")
    if type(timeout) not in {int, float} or not math.isfinite(timeout) or timeout <= 0:
        raise SolverValidationError("population_request_timeout_unavailable")
    if policy.get("retry_limit") != 1:
        raise SolverValidationError("population_retry_policy_invalid")


def claim(harness, run, *, takeover=False):
    """Acquire a durable epoch; reading a Run never implicitly takes ownership."""
    from .population_store import command

    claimed = command(harness, run["run_id"], "claim", owner_id=harness._instance_id,
                      takeover=takeover)
    pop = claimed["state"]["population"]
    owner = pop["owner"]
    harness._population_owner = deepcopy(owner if isinstance(owner, dict)
                                         else {"id": owner, "epoch": pop["epoch"]})
    return claimed


def resume_population(harness, run, problem, metadata):
    """Explicit resume takes over once, retaining uncertain identities and holds."""
    from .population_store import command

    if run["state"]["phase"] == "TERMINAL":
        return run
    run = claim(harness, run, takeover=True)
    if run["state"].get("status") in {"interrupted", "recovered_pending_validation"}:
        run = harness.commit_event(
            run["run_id"], expected_revision=run["state_revision"],
            event={"event_id": f"population-resumed-{run['state']['population']['epoch']}",
                   "type": "population_resumed"},
            state_updates={"status": "running"},
        )
    retry = metadata.get("retry_call")
    if retry is not None:
        run = command(harness, run["run_id"], "retry", retry_call=retry)
    run = command(harness, run["run_id"], "patch", updates={"paused_reason": None})
    return drive_population(harness, run, problem)


def advance_population(harness, run, problem, metadata):
    """One transition in the existing product controller; no separate solve loop."""
    from .finalize import run_finalization
    from .planning import generate_initial_plan
    from .population_budget import bind_population_action
    from .population_runtime import register_plans, tick

    if run["state"]["phase"] == "TERMINAL":
        return run
    with bind_population_action(None, harness._population_owner):
        if run["state"]["phase"] == "PLAN":
            run = _ensure_closing_reserve(harness, run, problem)
            if run["state"]["phase"] == "TERMINAL":
                return run
            run = generate_initial_plan(harness, run, problem=problem,
                                        model_port=harness._model_port,
                                        config=harness._config, metadata=metadata)
        if run["state"]["phase"] == "STEP_EXECUTE":
            run = register_plans(harness, run, run["state"]["plan"])
        if run["state"]["phase"] == "POPULATION":
            run = tick(harness, run, problem)
        if run["state"]["phase"] == "FINAL_GENERATE":
            run = run_finalization(harness, run, problem=problem,
                                   model_port=harness._model_port,
                                   verifier_port=harness._verifier_port, config=harness._config)
            run = record_delivery(harness, run)
        return run


def drive_population(harness, run, problem):
    """Keep using the existing phase controller until a durable yield or delivery."""
    from .controller import advance_product

    return advance_product(harness, run, problem)


def _ensure_closing_reserve(harness, run, problem):
    """Freeze a measured finalization floor before the first Planner request."""
    if run["state"].get("population", {}).get("closing_reserve"):
        return run
    from .population_store import command
    from .route_budget import expansion_budget

    policy = run["state"]["population_policy"]
    estimate = expansion_budget(
        harness, run, problem, harness._model_port,
        {"role": "planner", "problem": problem,
         "population_policy": {"version": policy["version"]}},
    )
    if estimate.get("preflight_valid") is not True:
        from .finalize import finish

        return finish(harness, run, "partial_aborted",
                      estimate.get("stop_reason") or "population_closing_reserve_unavailable")
    return command(
        harness, run["run_id"], "patch",
        updates={"closing_reserve": estimate["closing_reserve"]},
    )


def record_delivery(harness, run):
    """Keep mathematical delivery independent of unresolved physical requests."""
    from .final_binding import delivery_verification
    from .population_store import command

    state = run["state"]
    if state["phase"] != "TERMINAL":
        return run
    bound, _ = delivery_verification(run, state.get("final_response", ""))
    if bound:
        from .population_delivery import delivery_allowed

        bound, _ = delivery_allowed(harness._state_store._connection, state)
    delivery = {"status": "delivered" if bound else "not_delivered",
                "reason": "final_answer_bound" if bound else state.get("result_reason")}
    return command(harness, run["run_id"], "patch", updates={"delivery": delivery})
