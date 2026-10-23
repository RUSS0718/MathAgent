"""Strict, honest product presets; unvalidated full modes cannot be enabled."""

LIMITED_MODES = frozenset({"star_limited", "star_limited_best_effort"})

FULL_MODE_GAPS = (
    "isolated_python_output_guard",
    "accepted_step_checkpoint_recovery",
    "product_core_mechanism_acceptance",
    "final_evidence_review_binding",
)


def mode_identity(mode="legacy"):
    return {
        "solver_mode": mode,
        "preset_version": "sp11-v1" if mode == "star_limited_best_effort" else "sp02-v1",
        "missing_capabilities": list(FULL_MODE_GAPS) if mode != "legacy" else [],
    }


def validate_mode(mode, *, enabled, verification_mode="auto", options=None):
    from .workspace import WorkspaceError

    if not isinstance(mode, str) or mode not in {
        "legacy", "star_limited", "star_limited_best_effort", "star_reference", "star_best_effort"
    }:
        raise WorkspaceError("solver_mode_invalid", status=400)
    if options is not None:
        raise WorkspaceError("solver_options_unsupported", status=400)
    if mode in {"star_reference", "star_best_effort"}:
        raise WorkspaceError("star_prerequisites_unverified", status=503)
    if mode in LIMITED_MODES:
        if verification_mode == "off":
            raise WorkspaceError("star_review_required", status=400)
        if not enabled:
            raise WorkspaceError("star_not_enabled", status=503)
    return mode_identity(mode)


def capabilities(enabled):
    return [
        {**mode_identity(mode), "enabled": enabled if mode in LIMITED_MODES else mode == "legacy"}
        for mode in ("legacy", "star_limited", "star_limited_best_effort", "star_reference", "star_best_effort")
    ]
