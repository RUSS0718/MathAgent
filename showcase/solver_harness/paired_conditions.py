"""Condition validation for one allowlisted paired strategy difference."""

from copy import deepcopy

STRATEGIES = frozenset({"skills", "reexplore_after_replan", "candidate_registry", "best_effort"})
ROLES = {"model_port": "reasoner", "verifier_port": "verifier", "meta_port": "meta"}


def validate_conditions(control, variant, conditions, ports, feature):
    if feature not in STRATEGIES:
        raise ValueError("strategy_feature_not_allowed")
    configs = [deepcopy(control), deepcopy(variant)]
    values = []
    for config in configs:
        flags = config.setdefault("features", {})
        value = flags.pop(feature, False)
        if type(value) is not bool:
            raise ValueError("strategy_feature_must_be_boolean")
        values.append(value)
    if values[0] == values[1]:
        raise ValueError("strategy_feature_must_differ")
    if configs[0] != configs[1]:
        raise ValueError("common_conditions_differ")
    for key in ("max_model_calls", "max_tool_calls", "max_total_duration_seconds"):
        if type(control.get(key)) is not int or control[key] < 0:
            raise ValueError("explicit_hard_budget_required")
    models, transport = conditions.get("models"), conditions.get("transport")
    if not isinstance(models, dict) or not isinstance(transport, dict):
        raise ValueError("model_and_transport_conditions_required")
    for key in ("max_output_tokens", "timeout_seconds", "physical_attempts_per_call"):
        if type(transport.get(key)) is not int or transport[key] <= 0:
            raise ValueError("explicit_transport_limits_required")
    for key in ("max_http_attempts", "max_total_tokens"):
        if key in control and (type(control[key]) is not int or control[key] < 0):
            raise ValueError("invalid_hard_budget")
    left, right = ports
    if left.get("source") != right.get("source") or left.get("source") not in {
        "scripted",
        "offline_injected",
        "provider_live",
    }:
        raise ValueError("execution_sources_differ_or_missing")
    if (left.get("tool_port") is None) != (right.get("tool_port") is None):
        raise ValueError("tool_availability_differs")
    allowed_keys = {"source", "model_port", "verifier_port", "meta_port", "tool_port"}
    if any(set(arm) - allowed_keys for arm in ports):
        raise ValueError("unknown_port")
    if left.get("tool_port") is not None:
        if getattr(left["tool_port"], "registered_tools", None) != getattr(
            right["tool_port"], "registered_tools", None
        ) or getattr(left["tool_port"], "source", None) != getattr(
            right["tool_port"], "source", None
        ):
            raise ValueError("tool_registry_conditions_differ")
    for role_key in ROLES:
        for port in (left.get(role_key), right.get(role_key)):
            if port is None:
                continue
            if getattr(port, "adapter", None) is not None and left["source"] == "scripted":
                raise ValueError("adapter_cannot_claim_scripted_source")
    left_ids = {
        id(value) for key, value in left.items() if key.endswith("_port") and value is not None
    }
    right_ids = {
        id(value) for key, value in right.items() if key.endswith("_port") and value is not None
    }
    if left_ids & right_ids:
        raise ValueError("ports_must_be_independent_between_arms")
    identities = {}
    for key, role in ROLES.items():
        pair = [arm.get(key) for arm in ports]
        if (pair[0] is None) != (pair[1] is None):
            raise ValueError("role_availability_differs")
        if pair[0] is None:
            continue
        if pair[0] is pair[1]:
            raise ValueError("ports_must_be_independent_between_arms")
        declared = models.get(role, {})
        if not declared.get("model_id") or not declared.get("revision"):
            raise ValueError("model_version_required")
        identities[role] = []
        for port in pair:
            adapter = getattr(port, "adapter", None)
            client = getattr(adapter, "_client", None)
            actual = getattr(client, "model", None) or getattr(
                adapter, "model_id", getattr(port, "model_id", None)
            )
            if actual is not None and actual != declared["model_id"]:
                raise ValueError("observable_model_identity_mismatch")
            observed_revision = getattr(
                port, "model_revision", getattr(client, "model_revision", None)
            )
            if observed_revision is not None and observed_revision != declared["revision"]:
                raise ValueError("observable_model_revision_mismatch")
            identities[role].append(actual)
            if adapter is not None:
                observed = (
                    adapter.max_tokens,
                    adapter.client_timeout
                    if adapter.client_timeout is not None
                    else getattr(client, "timeout", None),
                    adapter.client_retry
                    if adapter.client_retry is not None
                    else getattr(client, "retry", None),
                )
                expected = tuple(
                    transport[key]
                    for key in (
                        "max_output_tokens",
                        "timeout_seconds",
                        "physical_attempts_per_call",
                    )
                )
                if observed != expected:
                    raise ValueError("observable_transport_limits_mismatch")
    if left.get("tool_port") is not None and left.get("tool_port") is right.get("tool_port"):
        raise ValueError("tool_ports_must_be_independent")
    return {
        "declared": "equal_except_strategy",
        "observable_model_ids": identities,
        "model_revision_verification": "declared_only",
        "strategy_values": values,
        "identity_status": "observed"
        if identities
        and all(all(value is not None for value in pair) for pair in identities.values())
        else "unknown",
    }
