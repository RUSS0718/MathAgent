"""Fail-closed, per-call stream selection for the explicit STAR product path."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from urllib.parse import urlsplit

from .request_transport import INTERN_S2_LIVE_ENDPOINT


@dataclass(frozen=True)
class StreamProfile:
    """One exact request profile with an explicit evidence class."""

    endpoint: str
    model: str
    temperature: float
    max_tokens: int
    thinking_mode: bool | None
    messages_schema: tuple[tuple[str, tuple[str, ...]], ...]
    evidence_kind: str
    status: str
    schema_fingerprint: str | None = None
    payload_keys: frozenset[str] = frozenset({
        "model", "messages", "stream", "temperature", "max_tokens", "thinking_mode",
    })


# Provider-live profiles are added only after a separately registered probe.
VERIFIED_STREAM_PROFILES: tuple[StreamProfile, ...] = ()


def _message_shape(messages):
    """Describe message structure without retaining prompt text."""
    if not isinstance(messages, (list, tuple)):
        return None
    shape = []
    for message in messages:
        if not isinstance(message, dict):
            return None
        role = message.get("role")
        if not isinstance(role, str):
            return None
        shape.append((role, tuple(sorted(message.keys()))))
    return tuple(shape)


def _controlled_endpoint(client, profile):
    """Keep synthetic profiles confined to explicitly loopback clients."""
    target = urlsplit(profile.endpoint)
    return (
        profile.evidence_kind == "controlled_test"
        and profile.status == "controlled_test"
        and getattr(client, "loopback_only", False) is True
        and target.scheme == "http"
        and target.hostname in {"127.0.0.1", "localhost", "::1"}
    )


def _profile_identity(profile):
    """Return the complete allow-list entry used for durable Run identity."""
    return {
        "endpoint": profile.endpoint,
        "model": profile.model,
        "temperature": profile.temperature,
        "max_tokens": profile.max_tokens,
        "thinking_mode": profile.thinking_mode,
        "messages_schema": profile.messages_schema,
        "payload_keys": sorted(profile.payload_keys),
        "evidence_kind": profile.evidence_kind,
        "schema_fingerprint": profile.schema_fingerprint,
        "status": profile.status,
    }


def _fingerprint(value):
    """Hash a canonical JSON value without exposing its configuration contents."""
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def profile_set_fingerprint(profiles=None):
    """Identify the full configured allow-list, independent of entry order."""
    configured = VERIFIED_STREAM_PROFILES if profiles is None else profiles
    identities = sorted(_fingerprint(_profile_identity(profile)) for profile in configured)
    return _fingerprint(identities)


def _payload_details(adapter, messages):
    """Return the serialized stream fields used by the existing stream adapter."""
    client = adapter._get_client()
    model = getattr(client, "model", None) or adapter.model_id
    thinking_mode = adapter.thinking_mode
    if thinking_mode is None:
        thinking_mode = getattr(client, "thinking_mode", None)
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": adapter.temperature,
        "max_tokens": adapter.max_tokens,
    }
    if thinking_mode is not None:
        payload["thinking_mode"] = thinking_mode
    return client, payload, thinking_mode


def select_transport(adapter, messages, *, policy="legacy", native_tools=False, profiles=None,
                     schema_fingerprint=None):
    """Choose one transport before dispatch and return safe audit metadata."""
    if policy not in {"legacy", "stream_first"}:
        raise ValueError("star_transport_policy_invalid")
    configured_profiles = VERIFIED_STREAM_PROFILES if profiles is None else profiles
    profile_set_id = profile_set_fingerprint(configured_profiles)
    if policy == "legacy":
        if native_tools:
            return {
                "policy": policy,
                "transport": "nonstream",
                "reason": "provider_native_tools_unsupported_with_stream",
                "evidence_kind": "documented",
                "profile_set_fingerprint": profile_set_id,
            }
        return {
            "policy": policy,
            "transport": "legacy",
            "reason": None,
            "evidence_kind": None,
            "profile_set_fingerprint": profile_set_id,
        }

    client, payload, thinking_mode = _payload_details(adapter, messages)
    endpoint = getattr(client, "api_base", None)
    model = payload["model"]
    shape = _message_shape(messages)

    if native_tools:
        return {
            "policy": policy,
            "transport": "reject",
            "reason": "provider_native_tools_unsupported_with_stream",
            "evidence_kind": "documented",
            "new_run_required": True,
            "profile_set_fingerprint": profile_set_id,
        }

    for profile in configured_profiles:
        if profile.status == "provider_live_verified":
            valid_evidence = profile.evidence_kind == "provider_live" and any(
                _profile_identity(profile) == _profile_identity(verified)
                for verified in VERIFIED_STREAM_PROFILES
            )
        else:
            valid_evidence = _controlled_endpoint(client, profile)
        if not valid_evidence:
            continue
        if (
            endpoint == profile.endpoint
            and model == profile.model
            and adapter.temperature == profile.temperature
            and adapter.max_tokens == profile.max_tokens
            and (type(thinking_mode) is bool or thinking_mode is None)
            and thinking_mode == profile.thinking_mode
            and shape == profile.messages_schema
            and profile.schema_fingerprint == schema_fingerprint
            and frozenset(payload) == profile.payload_keys
        ):
            if callable(getattr(adapter, "stream_complete", None)):
                return {
                    "policy": policy,
                    "transport": "stream",
                    "reason": "profile_match",
                    "evidence_kind": profile.evidence_kind,
                    "profile_fingerprint": _fingerprint(_profile_identity(profile)),
                    "profile_set_fingerprint": profile_set_id,
                }
            return {"policy": policy, "transport": "reject", "reason": "stream_adapter_unavailable",
                    "evidence_kind": profile.evidence_kind, "new_run_required": True,
                    "profile_fingerprint": _fingerprint(_profile_identity(profile)),
                    "profile_set_fingerprint": profile_set_id}

    reason = "unknown_endpoint" if endpoint not in {
        INTERN_S2_LIVE_ENDPOINT,
        *(profile.endpoint for profile in configured_profiles),
    } else "provider_profile_unverified"
    return {
        "policy": policy,
        "transport": "reject",
        "reason": reason,
        "evidence_kind": "not_verified",
        "new_run_required": True,
        "profile_set_fingerprint": profile_set_id,
    }
