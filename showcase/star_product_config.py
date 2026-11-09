"""Trusted server options for existing limited STAR mechanisms, never HTTP options."""

from collections.abc import Mapping

from .tools import ToolRegistry

OPTIONAL_FEATURES = frozenset({
    "final_generation", "final_solution_review", "local_code_tool", "meta_guidance",
    "reexplore_after_replan", "skills", "stream_activity", "context_pack",
    "problem_spec", "progress_scheduling",
    "proof_graph", "serial_routes", "concurrent_routes",
})
EXPERIMENTAL_FEATURES = frozenset({"planner_checkpoints", "reasoner_checkpoints"})
CORE_FEATURES = frozenset({
    "star_routing", "persistent_sessions", "stream_recovery",
    *(OPTIONAL_FEATURES - {"stream_activity", "context_pack", "problem_spec", "progress_scheduling", "proof_graph", "serial_routes", "concurrent_routes"}),
})
SUPPORTED_FEATURES = CORE_FEATURES | OPTIONAL_FEATURES | EXPERIMENTAL_FEATURES


def full_config(budget, features=None, context_capacity=None):
    if features is not None and (not isinstance(features, Mapping) or any(
        key not in SUPPORTED_FEATURES | {"strict_completion"} or type(value) is not bool for key, value in features.items()
    )):
        raise ValueError("star_full_features_invalid")
    enabled = dict.fromkeys(CORE_FEATURES, True) if features is None else dict(features)
    _freeze_serial_route_dependencies(enabled)
    if enabled.get("progress_scheduling") is True and enabled.get("problem_spec") is not True:
        raise ValueError("progress_scheduling_requires_problem_spec")
    config = {
        "features": enabled, "allowed_tools": ["polynomial_check", "python_math"],
        "max_model_calls": budget.max_model_calls, "max_tool_calls": budget.max_tool_calls,
        "max_total_duration_seconds": max(1, int(budget.max_runtime_seconds)),
        "max_explore_rounds": 2, "max_challenge_rounds": 5,
        "max_replans": 3, "max_final_solution_retries": 2,
    }
    if enabled.get("context_pack") is True:
        if context_capacity is None:
            raise ValueError("context_capacity_required")
        config["context_capacity"] = context_capacity
    return config


def core_gaps(config):
    features = config.get("features", {})
    missing = [f"feature:{key}" for key in sorted(CORE_FEATURES) if features.get(key) is not True]
    if "python_math" not in config.get("allowed_tools", []):
        missing.append("isolated_python_registry")
    return missing


def limited_config(budget, features=None, registry=None, context_capacity=None):
    if features is not None and (not isinstance(features, Mapping) or any(
        key not in OPTIONAL_FEATURES | EXPERIMENTAL_FEATURES | {"strict_completion"} or type(value) is not bool for key, value in features.items()
    )):
        raise ValueError("star_features_invalid")
    if registry is not None and not isinstance(registry, ToolRegistry):
        raise ValueError("star_registry_invalid")
    enabled = {"star_routing": True, "persistent_sessions": True, "stream_recovery": True,
               **(features or {})}
    if enabled.get("concurrent_routes") is True:
        raise ValueError("concurrent_routes_requires_star_population_preset")
    _freeze_serial_route_dependencies(enabled)
    if enabled.get("problem_spec") is True and (
        enabled.get("final_generation") is not True
        or enabled.get("final_solution_review") is not True
    ):
        raise ValueError("problem_spec_requires_final_generation_and_review")
    if enabled.get("local_code_tool") and registry is None:
        raise ValueError("star_registry_required")
    tools = ["polynomial_check"] if registry else []
    if registry is not None and hasattr(registry, "container_python_executor"):
        tools.append("python_math")
    if enabled.get("progress_scheduling") is True and enabled.get("problem_spec") is not True:
        raise ValueError("progress_scheduling_requires_problem_spec")
    config = {
        "features": enabled, "allowed_tools": tools,
        "max_model_calls": budget.max_model_calls, "max_tool_calls": budget.max_tool_calls,
        "max_total_duration_seconds": max(1, int(budget.max_runtime_seconds)), "max_explore_rounds": 2,
        "max_challenge_rounds": 3,
    }
    if enabled.get("context_pack") is True:
        if context_capacity is None:
            raise ValueError("context_capacity_required")
        config["context_capacity"] = context_capacity
    return config


def population_config(budget, capacity, *, evidence_kind, request_timeout_seconds):
    """Build the explicit concurrent preset from trusted, controlled capacity evidence."""
    if not isinstance(capacity, Mapping):
        raise ValueError("population_capacity_required")
    required = {"service_id", "max_inflight", "worker_slots", "evidence_ref", "status"}
    if not required <= set(capacity):
        raise ValueError("population_capacity_invalid")
    if (not isinstance(capacity["service_id"], str) or not capacity["service_id"].strip()
            or not isinstance(capacity["evidence_ref"], str) or not capacity["evidence_ref"].strip()
            or type(capacity["max_inflight"]) is not int or capacity["max_inflight"] < 1
            or type(capacity["worker_slots"]) is not int
            or capacity["worker_slots"] < capacity["max_inflight"]):
        raise ValueError("population_capacity_invalid")
    evidence_ok = ((evidence_kind == "fault_injection" and capacity["status"] == "controlled")
                   or (evidence_kind == "live" and capacity["status"] == "verified"))
    if not evidence_ok:
        raise ValueError("population_capacity_unverified")
    if (type(request_timeout_seconds) not in {int, float}
            or request_timeout_seconds <= 0):
        raise ValueError("population_request_timeout_unavailable")
    features = {
        "problem_spec": True, "proof_graph": True, "progress_scheduling": True,
        "final_generation": True, "final_solution_review": True,
        "serial_routes": False,
    }
    config = limited_config(budget, features)
    config["features"]["concurrent_routes"] = True
    config["max_http_attempts"] = budget.max_http_attempts
    config["max_tokens"] = budget.max_tokens
    config["max_runtime_seconds"] = budget.max_runtime_seconds
    config["max_challenge_rounds"] = 1
    config["population_policy"] = {
        "enabled": True, "version": "concurrent-aprs-v1",
        "schema_version": "population-v1", "capacity": dict(capacity),
        "request_timeout_seconds": request_timeout_seconds, "retry_limit": 1,
    }
    return config


def _freeze_serial_route_dependencies(features):
    if features.get("serial_routes") is not True:
        return
    if features.get("problem_spec") is not True:
        raise ValueError("serial_routes_requires_problem_spec")
    if features.get("progress_scheduling") is False:
        raise ValueError("serial_routes_requires_progress_scheduling")
    features["progress_scheduling"] = True
