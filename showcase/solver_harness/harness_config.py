"""Solver Harness input normalization, identity hashing and validation errors."""

import hashlib
import json
import uuid
from collections.abc import Mapping
from typing import Any


class SolverHarnessError(RuntimeError):
    """Base error for Solver Harness operations."""


class SolverValidationError(SolverHarnessError, ValueError):
    """Raised when a Solver Harness input is invalid."""


def _run_id(metadata: Mapping[str, Any] | None) -> str:
    requested = None if metadata is None else metadata.get("run_id")
    if requested is None:
        return f"solver_{uuid.uuid4().hex}"
    if not isinstance(requested, str) or not requested.strip():
        raise SolverValidationError("metadata.run_id must be a non-empty string")
    return requested.strip()


def _normalize_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    if config is None:
        return {}
    if not isinstance(config, Mapping):
        raise SolverValidationError("config must be a mapping")
    try:
        normalized = json.loads(
            json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
    except (TypeError, ValueError) as exc:
        raise SolverValidationError("config must be JSON serializable") from exc
    if not isinstance(normalized, dict):
        raise SolverValidationError("config must be a mapping")
    return normalized


def _hash_json(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_json_mapping(value: Mapping[str, Any] | None, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SolverValidationError(f"{label} must be a mapping")
    try:
        normalized = json.loads(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
    except (TypeError, ValueError) as exc:
        raise SolverValidationError(f"{label} must be JSON serializable") from exc
    if not isinstance(normalized, dict):
        raise SolverValidationError(f"{label} must be a mapping")
    return normalized


def _non_negative_config_int(config: Mapping[str, Any], key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SolverValidationError(f"config.{key} must be a non-negative integer")
    return value


def _positive_config_int(config: Mapping[str, Any], key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SolverValidationError(f"config.{key} must be a positive integer")
    return value
