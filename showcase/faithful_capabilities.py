"""Public admission for autonomous input; never infer readiness from a label."""


def faithful_capabilities(config, solver_modes, pipeline):
    """Describe the actual default route and fail closed on missing mechanisms."""
    enabled = config.get("SHOWCASE_FAITHFUL_AUTONOMOUS") is True
    reference = next((mode for mode in solver_modes
                      if mode["solver_mode"] == "star_reference"), {})
    features = getattr(pipeline, "full_config", {}).get("features", {})
    reasons = list(reference.get("missing_capabilities", [])) if enabled else []
    if enabled and features.get("auto_problem_spec") is not True:
        reasons.append("auto_problem_spec_disabled")
    return {
        "version": "faithful-capabilities-v1",
        "maturity": "experimental",
        "features": {key: value is True for key, value in features.items()},
        "optional_limitations": [
            reason for available, reason in (
                (config.get("SHOWCASE_FORMAL_BACKEND") is not None, "formal_not_configured"),
                (config.get("SHOWCASE_STAR_POPULATION_ENABLED") is True, "population_not_enabled"),
            ) if not available
        ],
        "enabled": enabled,
        "ready": enabled and reference.get("enabled") is True and not reasons,
        "solver_mode": "star_reference",
        "input_mode": "automatic",
        "unavailable_reasons": reasons,
    }
