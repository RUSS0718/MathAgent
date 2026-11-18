"""Explicit product presets; runtime readiness never implies release acceptance."""

import hashlib
import json

LIMITED_MODE_ORDER = ("star_limited", "star_limited_best_effort", "star_population")
FULL_MODE_ORDER = ("star_reference", "star_best_effort")
LIMITED_MODES = frozenset(LIMITED_MODE_ORDER)
FULL_MODES = frozenset(FULL_MODE_ORDER)
STAR_MODES = LIMITED_MODES | FULL_MODES
BEST_EFFORT_MODES = frozenset({"star_limited_best_effort", "star_best_effort"})
# 公共模式枚举的稳定展示顺序；合法模式集合与 capabilities 记录均由此派生。
MODE_ORDER = ("legacy", *LIMITED_MODE_ORDER, *FULL_MODE_ORDER)


def mode_identity(mode="legacy", config=None):
    from .star_product_config import core_gaps

    identity = {
        "solver_mode": mode,
        "preset_version": ("concurrent-aprs-v1" if mode == "star_population" else
                           "sp13-v1" if mode in FULL_MODES else
                           "sp11-v1" if mode == "star_limited_best_effort" else "sp02-v1"),
        # 无 preset 配置＝模式默认关闭，不逐项枚举特性缺口；有配置时按实际配置列。
        "missing_capabilities": ((["star_not_enabled"] if config is None else
                                   _population_gaps(config) if mode == "star_population" else core_gaps(config))
                                 if mode in LIMITED_MODES else []),
    }
    if mode in STAR_MODES and config is not None and config.get("acceptance_mode") == "handoff":
        identity.update(acceptance_mode="handoff", preset_version="handoff-v1")
    if mode == "star_population" and isinstance(config, dict):
        frozen = {
            "population_policy": config.get("population_policy"),
            "transport_identity": config.get("transport_identity"),
            "features": {key: value for key, value in config.get("features", {}).items()
                         if key != "candidate_registry"},
            "budget": {key: config.get(key) for key in (
                "max_model_calls", "max_http_attempts", "max_tool_calls",
                "max_tokens", "max_total_duration_seconds", "max_runtime_seconds",
                "max_challenge_rounds",
            )},
        }
        identity["population_policy_hash"] = hashlib.sha256(
            json.dumps(frozen, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    return identity


def validate_mode(mode, *, enabled, verification_mode="auto", options=None, pipeline=None):
    from .workspace import WorkspaceError

    if not isinstance(mode, str) or mode not in STAR_MODES | {"legacy"}:
        raise WorkspaceError("solver_mode_invalid", status=400)
    if options is not None:
        raise WorkspaceError("solver_options_unsupported", status=400)
    if mode in STAR_MODES:
        if (getattr(pipeline, "acceptance_mode", "strict") == "handoff"
                and mode in BEST_EFFORT_MODES):
            raise WorkspaceError("handoff_best_effort_forbidden", status=400)
        if verification_mode == "off":
            raise WorkspaceError("star_review_required", status=400)
        if mode == "star_population" and pipeline is not None:
            gaps = pipeline.population_gaps()
            if gaps:
                raise WorkspaceError("population_prerequisites_unverified", status=503)
        mode_enabled = (pipeline.mode_enabled(mode) if pipeline is not None and hasattr(pipeline, "mode_enabled")
                        else enabled)
        if not mode_enabled:
            raise WorkspaceError("star_prerequisites_unverified" if mode in FULL_MODES
                                 else "star_not_enabled", status=503)
    if mode in FULL_MODES:
        if pipeline is None or pipeline.full_gaps(probe=True):
            raise WorkspaceError("star_prerequisites_unverified", status=503)
    return mode_identity(mode, None if pipeline is None else pipeline.preset_config(mode))


def capabilities(enabled, pipeline=None):
    if pipeline is None:
        gaps, readiness = ["full_mode_not_enabled"], {}
    else:
        gaps, readiness = pipeline.full_gaps(), pipeline.readiness_state()
    preflight = {key: readiness[key] for key in (
        "run_id", "image_id", "receipt_ref", "budget_ref") if readiness.get(key) is not None} or None
    records = []
    for mode in MODE_ORDER:
        config = None if pipeline is None else pipeline.preset_config(mode)
        mode_enabled = (pipeline.mode_enabled(mode) if pipeline is not None and hasattr(pipeline, "mode_enabled")
                        else enabled)
        record = {**mode_identity(mode, config),
                  "enabled": (not gaps if mode in FULL_MODES else
                              not _population_gaps(config) if mode == "star_population" else
                              mode_enabled if mode in LIMITED_MODES else True)}
        if mode in FULL_MODES:
            record["missing_capabilities"] = gaps
            # Observed admission state only; the receipt is independently verifiable bytes.
            if preflight is not None:
                record["last_preflight"] = preflight
        if getattr(pipeline, "acceptance_mode", "strict") == "handoff" and mode in BEST_EFFORT_MODES:
            record.update(enabled=False, missing_capabilities=["handoff_best_effort_forbidden"])
        records.append(record)
    return records


def _population_gaps(config):
    if not isinstance(config, dict) or not isinstance(config.get("population_policy"), dict):
        return ["population_not_enabled"]
    required = {"star_routing", "persistent_sessions", "stream_recovery", "problem_spec",
                "proof_graph", "progress_scheduling", "final_generation",
                "final_solution_review", "concurrent_routes"}
    features = config.get("features", {})
    gaps = [f"feature:{key}" for key in sorted(required) if features.get(key) is not True]
    policy = config["population_policy"]
    if (policy.get("enabled") is not True
            or policy.get("version") != "concurrent-aprs-v1"
            or policy.get("schema_version") != "population-v1"):
        gaps.append("population_policy_version_unavailable")
    capacity = policy.get("capacity")
    if (not isinstance(capacity, dict)
            or capacity.get("status") not in {"controlled", "verified"}
            or type(capacity.get("max_inflight")) is not int or capacity["max_inflight"] < 1
            or type(capacity.get("worker_slots")) is not int
            or capacity["worker_slots"] < capacity["max_inflight"]
            or not isinstance(capacity.get("service_id"), str) or not capacity["service_id"].strip()
            or not isinstance(capacity.get("evidence_ref"), str) or not capacity["evidence_ref"].strip()):
        gaps.append("population_capacity_unverified")
    timeout = policy.get("request_timeout_seconds")
    if type(timeout) not in {int, float} or timeout <= 0:
        gaps.append("population_request_timeout_unavailable")
    if policy.get("retry_limit") != 1:
        gaps.append("population_retry_policy_invalid")
    return gaps
