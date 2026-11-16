"""Opt-in dependency qualification over the existing ProblemSpec and PLAN path."""

from .harness_config import SolverValidationError

VERSION = "objective-dependency-routing-v1"
POLICY = {"name": "objective-dependency-routing", "version": 1}


def unverified_findings(state):
    """Label reference material without reconstructing or upgrading legacy sources."""
    from copy import deepcopy

    return [{**deepcopy(item), "provenance": "unverified_exploration",
             "source": deepcopy(item.get("source") or {"status": "unknown"})}
            for item in state.get("exploration_findings", [])]


def validate_config(config):
    """Reject unsupported policies without adding defaults to legacy identity."""
    if "routing_policy_version" not in config:
        return
    features = config.get("features", {})
    if config["routing_policy_version"] != VERSION:
        raise SolverValidationError("routing_policy_version_invalid")
    if (any(features.get(key) is not True for key in (
            "adaptive_solving", "problem_spec", "auto_problem_spec", "star_routing",
            "final_generation", "final_solution_review"))
            or config.get("acceptance_mode", "strict") != "strict"
            or features.get("concurrent_routes") is True):
        raise SolverValidationError("routing_policy_prerequisites_required")


def planning_requirement(state):
    """Read current normalized spec edges only for Runs frozen under this policy."""
    policy = state.get("routing_policy")
    if policy is None:
        return None
    if policy != POLICY:
        raise SolverValidationError("routing_policy_version_invalid")
    spec = state.get("problem_spec") or {}
    if (any(item.get("prerequisite_ids") for item in spec.get("root_obligations", []))
            or any(item.get("dependencies") for item in spec.get("auxiliary_goals", []))):
        return "objective_dependencies"
    return None


def require_plan(harness, run):
    """Route eligible pre-plan work once, after control and unknown guards."""
    from ..run_control import check_control
    from ..star_product_recovery import recovery_projection
    from .finalize import commit

    state = run["state"]
    if not state.get("routing_policy") or state["phase"] == "TERMINAL":
        return run
    check_control()
    recovery = recovery_projection(run)
    if (recovery["unknown_calls"] or recovery["unknown_tools"]
            or state.get("status") in {"interrupted", "recovered_pending_validation"}
            or state.get("clarification", {}).get("status") == "waiting"):
        return run
    reason = planning_requirement(state)
    if reason is None or state["phase"] not in {"SETUP", "EXPLORE", "EXPLORE_REVIEW"}:
        return run
    policy = state.get("adaptive_solving") or {
        "version": "adaptive-solving-v1", "corrections": 0}
    return commit(harness, run, "adaptive_planning_required", {
        "phase": "PLAN", "adaptive_solving": {**policy, "reason": reason}},
        reason=reason, next_phase="PLAN", policy_version=VERSION,
        specification_version=state["specification_version"])
