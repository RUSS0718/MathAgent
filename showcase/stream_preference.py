"""Fail-closed, per-call stream selection for the explicit STAR product path."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
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


_VERIFIED_ENDPOINT = INTERN_S2_LIVE_ENDPOINT
_VERIFIED_MESSAGE = ("system", ("content", "role"))
_VERIFIED_USER_MESSAGE = ("user", ("content", "role"))
_VERIFIED_MESSAGE_SHAPES = (
    (_VERIFIED_MESSAGE, _VERIFIED_USER_MESSAGE),
    (_VERIFIED_MESSAGE, _VERIFIED_MESSAGE, _VERIFIED_MESSAGE, _VERIFIED_MESSAGE,
     _VERIFIED_USER_MESSAGE),
)
_SHAPE_2_SCHEMA_FINGERPRINTS = (
    "89fbfab654098a2025a0b69375f8dc8a7d8000391507639243712ca85a3a1473",
    "54ac692b082da9544bf9ee6ebc6c71cbf38396b8863aeb2e9d932de7f2cb6c10",
    "edaea8b9ad088955e19001ef3b3bc6479028b604003ddf6dee7feeef56507aec",
)
_SHAPE_5_SCHEMA_FINGERPRINTS = (
    *_SHAPE_2_SCHEMA_FINGERPRINTS,
    "47d696ba141a0df8916096620b35e322e402c59c41a80fca7b268a4c2ee2efee",
    "8836d710fac9532e05ef506e19a3da7fee87bb4a96b588396dd9842e83d986ef",
    "f45df661a9c9ae45dee4ed363ed244c934a60b951d5cd4eeb2464b3fd2606eb7",
    "db00d390d3dd387091b0ead73c45125c45094bf98ea7f04df5dce1257dd238ee",
    "818c4d7d0098f6117fa023907d53dc161f8d45bfbd847285ff07d0d890877b87",
    "e5b9cd4d259add409204822298e4ed299c8eb2a02f27a359b688058b90721a4f",
)

# These thirteen immutable entries cover ten schemas across only the probe-tested
# message shapes. Any other endpoint/configuration/schema remains unverified.
VERIFIED_STREAM_PROFILES: tuple[StreamProfile, ...] = tuple(
    StreamProfile(
        endpoint=_VERIFIED_ENDPOINT,
        model="intern-s2",
        temperature=0.2,
        max_tokens=32_768,
        thinking_mode=False,
        messages_schema=messages_schema,
        evidence_kind="provider_live",
        status="provider_live_verified",
        schema_fingerprint=schema_fingerprint,
    )
    for schema_fingerprint, message_shapes in (
        *((fingerprint, (_VERIFIED_MESSAGE_SHAPES[0],))
          for fingerprint in _SHAPE_2_SCHEMA_FINGERPRINTS),
        *((fingerprint, (_VERIFIED_MESSAGE_SHAPES[1],))
          for fingerprint in _SHAPE_5_SCHEMA_FINGERPRINTS),
        ("9806bf844a1871e77a826e802027f93929767e99a7bd3bc1366318abf4be7590",
         (_VERIFIED_MESSAGE_SHAPES[1],)),
    )
    for messages_schema in message_shapes
)


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
                "capability_limit": "native_tools_require_nonstream",
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
            "capability_limit": "native_tools_require_nonstream",
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
