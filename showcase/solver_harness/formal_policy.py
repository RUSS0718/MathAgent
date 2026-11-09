"""Validation for an explicitly frozen formal verification policy."""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping
from typing import Any


class FormalPolicyError(ValueError):
    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


POLICY_KEYS = frozenset({
    "enabled", "requested_backend", "allowed_backends", "require_formal",
    "timeout_seconds", "max_output_bytes", "resource_limits", "allowed_axioms",
    "environment", "target",
})
TARGET_KEYS = frozenset({
    "domain", "variables", "lhs", "rhs", "quantifiers", "assumptions",
    "direction", "conclusion", "hash", "_lean_lhs", "_lean_rhs",
})


def normalize_formal_policy(
    value: Any, *, configured: bool, server_template: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Freeze a request policy against the trusted server capability profile."""
    if not configured:
        raise FormalPolicyError("formal_verification_disabled")
    if not isinstance(value, Mapping):
        raise FormalPolicyError("formal_policy_invalid")
    if set(value) - POLICY_KEYS:
        raise FormalPolicyError("formal_policy_invalid")
    if server_template is not None:
        if not isinstance(server_template, Mapping) or server_template.get("enabled") is not True:
            raise FormalPolicyError("formal_verification_disabled")
        for key in ("timeout_seconds", "max_output_bytes", "resource_limits", "allowed_axioms", "environment"):
            if key in value and value[key] != server_template.get(key):
                raise FormalPolicyError(f"formal_policy_{key}_conflict")
        if "target" not in value:
            raise FormalPolicyError("formal_target_invalid")
        requested_allowed = value.get("allowed_backends", server_template.get("allowed_backends"))
        registered = server_template.get("allowed_backends")
        if (not isinstance(registered, list) or not isinstance(requested_allowed, list)
                or any(name not in registered for name in requested_allowed)):
            raise FormalPolicyError("formal_backend_not_allowed")
        value = {**dict(server_template), **dict(value), "allowed_backends": registered}
    if value.get("enabled") is not True:
        raise FormalPolicyError("formal_policy_invalid")
    backend = value.get("requested_backend")
    if not isinstance(backend, str) or not backend.strip():
        raise FormalPolicyError("formal_backend_required")
    allowed = value.get("allowed_backends")
    if (not isinstance(allowed, list) or not allowed
            or any(not isinstance(item, str) or not item for item in allowed)
            or backend not in allowed):
        raise FormalPolicyError("formal_backend_not_allowed")
    timeout = value.get("timeout_seconds")
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or timeout <= 0):
        raise FormalPolicyError("formal_timeout_invalid")
    output_limit = value.get("max_output_bytes")
    if isinstance(output_limit, bool) or not isinstance(output_limit, int) or output_limit <= 0:
        raise FormalPolicyError("formal_output_limit_invalid")
    resources = value.get("resource_limits")
    if not isinstance(resources, Mapping):
        raise FormalPolicyError("formal_resources_invalid")
    axioms = value.get("allowed_axioms")
    if not isinstance(axioms, list) or any(not isinstance(item, str) or not item for item in axioms):
        raise FormalPolicyError("formal_axioms_invalid")
    environment = value.get("environment")
    if not isinstance(environment, Mapping):
        raise FormalPolicyError("formal_environment_invalid")
    target = value.get("target")
    if not isinstance(target, Mapping) or set(target) - TARGET_KEYS:
        raise FormalPolicyError("formal_target_invalid")
    normalized = copy.deepcopy(dict(value))
    normalized.update({
        "enabled": True,
        "backend": backend,
        "requested_backend": backend,
        "allowed_backends": list(dict.fromkeys(allowed)),
        "require_formal": value.get("require_formal") is True,
        "timeout_seconds": float(timeout),
        "max_output_bytes": output_limit,
        "resource_limits": dict((server_template or {}).get("resource_limits", resources)),
        "allowed_axioms": list(dict.fromkeys(
            (server_template or {}).get("allowed_axioms", axioms))),
        "environment": dict((server_template or {}).get("environment", environment)),
        "target": dict(target),
    })
    return normalized
