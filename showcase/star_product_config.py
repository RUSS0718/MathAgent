"""Trusted server options for existing limited STAR mechanisms, never HTTP options."""

from collections.abc import Mapping

from .tools import ToolRegistry

OPTIONAL_FEATURES = frozenset({
    "final_generation", "final_solution_review", "local_code_tool", "meta_guidance",
    "reexplore_after_replan", "skills",
})


def limited_config(budget, features=None, registry=None):
    if features is not None and (not isinstance(features, Mapping) or any(
        key not in OPTIONAL_FEATURES or type(value) is not bool for key, value in features.items()
    )):
        raise ValueError("star_features_invalid")
    if registry is not None and not isinstance(registry, ToolRegistry):
        raise ValueError("star_registry_invalid")
    enabled = {"star_routing": True, "persistent_sessions": True, "stream_recovery": True,
               **(features or {})}
    if enabled.get("local_code_tool") and registry is None:
        raise ValueError("star_registry_required")
    tools = ["polynomial_check"] if registry else []
    if registry is not None and hasattr(registry, "container_python_executor"):
        tools.append("python_math")
    return {
        "features": enabled, "allowed_tools": tools,
        "max_model_calls": budget.max_model_calls, "max_tool_calls": budget.max_tool_calls,
        "max_total_duration_seconds": max(1, int(budget.max_runtime_seconds)), "max_explore_rounds": 2,
    }
