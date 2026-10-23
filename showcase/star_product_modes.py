"""Explicit product presets; runtime readiness never implies release acceptance."""

LIMITED_MODES = frozenset({"star_limited", "star_limited_best_effort"})
FULL_MODES = frozenset({"star_reference", "star_best_effort"})
STAR_MODES = LIMITED_MODES | FULL_MODES
BEST_EFFORT_MODES = frozenset({"star_limited_best_effort", "star_best_effort"})


def mode_identity(mode="legacy", config=None):
    from .star_product_config import core_gaps

    return {
        "solver_mode": mode,
        "preset_version": ("sp13-v1" if mode in FULL_MODES else
                           "sp11-v1" if mode == "star_limited_best_effort" else "sp02-v1"),
        # 无 preset 配置＝模式默认关闭，不逐项枚举特性缺口；有配置时按实际配置列。
        "missing_capabilities": ((["star_not_enabled"] if config is None else core_gaps(config))
                                 if mode in LIMITED_MODES else []),
    }


def validate_mode(mode, *, enabled, verification_mode="auto", options=None, pipeline=None):
    from .workspace import WorkspaceError

    if not isinstance(mode, str) or mode not in {
        "legacy", "star_limited", "star_limited_best_effort", "star_reference", "star_best_effort"
    }:
        raise WorkspaceError("solver_mode_invalid", status=400)
    if options is not None:
        raise WorkspaceError("solver_options_unsupported", status=400)
    if mode in STAR_MODES:
        if verification_mode == "off":
            raise WorkspaceError("star_review_required", status=400)
        if not enabled:
            raise WorkspaceError("star_prerequisites_unverified" if mode in FULL_MODES
                                 else "star_not_enabled", status=503)
    if mode in FULL_MODES:
        if pipeline is None or pipeline.full_gaps(probe=True):
            raise WorkspaceError("star_prerequisites_unverified", status=503)
    return mode_identity(mode, getattr(pipeline, "config", None))


def capabilities(enabled, pipeline=None):
    gaps = pipeline.full_gaps() if pipeline is not None else ["full_mode_not_enabled"]
    readiness = getattr(pipeline, "readiness", None) or {}
    preflight = {key: readiness[key] for key in (
        "run_id", "image_id", "receipt_ref", "budget_ref") if readiness.get(key) is not None} or None
    records = []
    for mode in ("legacy", "star_limited", "star_limited_best_effort", "star_reference", "star_best_effort"):
        record = {**mode_identity(mode, getattr(pipeline, "config", None)),
                  "enabled": (not gaps if mode in FULL_MODES else
                              enabled if mode in LIMITED_MODES else True)}
        if mode in FULL_MODES:
            record["missing_capabilities"] = gaps
            # Observed admission state only; the receipt is independently verifiable bytes.
            if preflight is not None:
                record["last_preflight"] = preflight
        records.append(record)
    return records
