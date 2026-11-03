"""Frozen manifest parsing and zero-dispatch validation primitives."""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any
from urllib.parse import urlsplit

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_REVISION = re.compile(r"[0-9a-f]{40,64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")
_EXECUTABLE_EVIDENCE_KINDS = frozenset(
    {"loopback", "scripted", "fault_injection", "provider_live"}
)
_MANIFEST_KEYS = {
    "schema_version",
    "manifest_id",
    "evidence_kind",
    "source_identity",
    "model",
    "transport",
    "samples",
    "run_limits",
    "batch_limits",
    "stop_on",
    "authorization",
}
_SOURCE_KEYS = {"revision", "source_sha256", "dirty_status", "dirty_paths"}
_MODEL_KEYS = {
    "name",
    "thinking_mode",
    "temperature",
    "max_output_tokens",
    "request_timeout_seconds",
    "retry",
    "solver_mode",
    "verification_mode",
}
_SAMPLE_KEYS = {"id", "source_ref", "type", "input_sha256", "text_sha256"}
_RUN_LIMIT_KEYS = {
    "max_model_calls",
    "max_http_attempts",
    "max_tool_calls",
    "max_tokens",
    "max_runtime_seconds",
}
_BATCH_LIMIT_KEYS = {
    "runs",
    "logical_calls",
    "http_attempts",
    "tool_calls",
    "charged_tokens",
    "wall_seconds",
}
_REQUIRED_STOP_RULES = {
    "unknown_transport",
    "incomplete_or_unresolved_usage",
    "failure",
    "cancel",
    "hard_limit",
    "source_or_config_change",
    "ledger_or_binding_defect",
}


def canonical_json(value: Any) -> bytes:
    """Encode JSON deterministically for registration and evidence hashes."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def manifest_digest(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(manifest)).hexdigest()


def is_executable_evidence_kind(value: Any) -> bool:
    return isinstance(value, str) and value in _EXECUTABLE_EVIDENCE_KINDS


def validate_manifest(manifest: Any) -> dict[str, Any]:
    """Validate a complete v1 registration without importing runtime adapters."""
    if not isinstance(manifest, dict) or set(manifest) - {"usage_policy"} != _MANIFEST_KEYS:
        raise ValueError("experiment_manifest_invalid")
    try:
        if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
            raise ValueError
        if not _valid_identifier(manifest["manifest_id"]):
            raise ValueError
        if not _nonempty_string(manifest["evidence_kind"]):
            raise ValueError
        usage_policy = manifest.get("usage_policy", "required")
        if usage_policy not in {"required", "observe_only"} or (
            usage_policy == "observe_only" and manifest["evidence_kind"] != "provider_live"
        ):
            raise ValueError
        _validate_source(manifest["source_identity"])
        _validate_model(manifest["model"])
        _validate_transport(manifest["transport"])
        _validate_samples(manifest["samples"])
        _validate_limits(manifest["run_limits"], _RUN_LIMIT_KEYS, allow_runtime=True)
        _validate_limits(manifest["batch_limits"], _BATCH_LIMIT_KEYS, allow_runtime=False)
        _validate_stop_rules(manifest["stop_on"])
        _validate_authorization(manifest["authorization"])
        canonical_json(manifest)
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError("experiment_manifest_invalid") from None
    return manifest


def _validate_source(source: Any) -> None:
    if not isinstance(source, dict) or set(source) != _SOURCE_KEYS:
        raise ValueError
    if not isinstance(source["revision"], str) or not _REVISION.fullmatch(source["revision"]):
        raise ValueError
    if not _is_hash(source["source_sha256"]):
        raise ValueError
    if source["dirty_status"] not in {"clean", "dirty"}:
        raise ValueError
    paths = source["dirty_paths"]
    if not isinstance(paths, list) or any(not _nonempty_string(path) for path in paths):
        raise ValueError
    if paths != sorted(set(paths)) or (source["dirty_status"] == "clean") != (not paths):
        raise ValueError


def _validate_model(model: Any) -> None:
    if not isinstance(model, dict) or set(model) != _MODEL_KEYS:
        raise ValueError
    if not _nonempty_string(model["name"]):
        raise ValueError
    if type(model["thinking_mode"]) is not bool:
        raise ValueError
    temperature = model["temperature"]
    if type(temperature) not in {int, float} or not math.isfinite(temperature) or temperature < 0:
        raise ValueError
    for key in ("max_output_tokens", "request_timeout_seconds"):
        if type(model[key]) is not int or model[key] <= 0:
            raise ValueError
    if type(model["retry"]) is not int or model["retry"] < 0:
        raise ValueError
    if not _nonempty_string(model["solver_mode"]) or not _nonempty_string(model["verification_mode"]):
        raise ValueError


def _validate_transport(transport: Any) -> None:
    if not isinstance(transport, dict):
        raise ValueError
    policy = transport.get("policy")
    expected_keys = (
        {"policy", "profile_set_fingerprint", "calls"}
        if policy == "stream_first"
        else {"policy", "transport", "profile_set_fingerprint", "calls"}
    )
    if set(transport) != expected_keys or not _is_hash(transport.get("profile_set_fingerprint")):
        raise ValueError
    if policy == "legacy" and transport["transport"] != "nonstream":
        raise ValueError
    if policy not in {"stream_first", "legacy"}:
        raise ValueError
    calls = transport["calls"]
    if not isinstance(calls, list) or not calls:
        raise ValueError
    call_ids = []
    for call in calls:
        keys = (
            {"call_id", "profile_fingerprint"}
            if policy == "stream_first"
            else {"call_id", "transport", "reason", "capability_limit"}
        )
        if not isinstance(call, dict) or set(call) != keys:
            raise ValueError
        if not _valid_identifier(call["call_id"]):
            raise ValueError
        if policy == "stream_first":
            if not _is_hash(call["profile_fingerprint"]):
                raise ValueError
        elif (
            call["transport"] != "nonstream"
            or (call["reason"], call["capability_limit"])
            not in {
                ("provider_profile_unverified", "verified_stream_profiles_empty"),
                ("provider_native_tools_unsupported_with_stream", "native_tools_require_nonstream"),
            }
        ):
            raise ValueError
        call_ids.append(call["call_id"])
    if len(call_ids) != len(set(call_ids)):
        raise ValueError


def _validate_samples(samples: Any) -> None:
    if not isinstance(samples, list) or not samples:
        raise ValueError
    identifiers = []
    for sample in samples:
        if not isinstance(sample, dict) or set(sample) != _SAMPLE_KEYS:
            raise ValueError
        if not _valid_identifier(sample["id"]):
            raise ValueError
        if not _valid_source_ref(sample["source_ref"]) or not _nonempty_string(sample["type"]):
            raise ValueError
        if not _is_hash(sample["input_sha256"]) or not _is_hash(sample["text_sha256"]):
            raise ValueError
        identifiers.append(sample["id"])
    if len(identifiers) != len(set(identifiers)):
        raise ValueError


def _validate_limits(limits: Any, keys: set[str], *, allow_runtime: bool) -> None:
    if not isinstance(limits, dict) or set(limits) != keys:
        raise ValueError
    for key, value in limits.items():
        if key == "max_runtime_seconds" and allow_runtime:
            if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
                raise ValueError
        elif type(value) is not int or value <= 0:
            raise ValueError


def _validate_stop_rules(rules: Any) -> None:
    if (
        not isinstance(rules, list)
        or any(not _nonempty_string(rule) for rule in rules)
        or len(rules) != len(set(rules))
        or not _REQUIRED_STOP_RULES.issubset(rules)
    ):
        raise ValueError


def _validate_authorization(authorization: Any) -> None:
    if not isinstance(authorization, dict) or set(authorization) != {
        "scope",
        "execution_authorized",
    }:
        raise ValueError
    if not _nonempty_string(authorization["scope"]):
        raise ValueError
    if type(authorization["execution_authorized"]) is not bool:
        raise ValueError


def _valid_identifier(value: Any) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_source_ref(value: Any) -> bool:
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if value.startswith("https://"):
        try:
            parsed = urlsplit(value)
            return bool(parsed.hostname) and parsed.username is None and parsed.password is None
        except ValueError:
            return False
    return _IDENTIFIER.fullmatch(value) is not None
