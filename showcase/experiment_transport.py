"""Preflight adapter for #124's frozen stream profile identities."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit

from .stream_preference import (
    VERIFIED_STREAM_PROFILES,
    _fingerprint,
    _profile_identity,
    profile_set_fingerprint,
)

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")


class ExperimentTransportAdapter:
    """Validate one Run against #124's exact policy and profile identities."""

    def __init__(self, profiles: Sequence[Any] | None = None) -> None:
        self.profiles = tuple(VERIFIED_STREAM_PROFILES if profiles is None else profiles)
        try:
            self.profile_set_fingerprint = profile_set_fingerprint(self.profiles)
            self.profile_fingerprints = {
                _fingerprint(_profile_identity(profile))
                for profile in self.profiles
                if self._trusted_profile(profile)
            }
            if len(self.profile_fingerprints) != len(self.profiles):
                raise ValueError
        except (AttributeError, TypeError, ValueError):
            raise ValueError("experiment_transport_profile_invalid") from None

    def validate_manifest_transport(self, transport: dict[str, Any]) -> None:
        try:
            if not isinstance(transport, dict):
                raise ValueError
            policy = transport.get("policy")
            if transport.get("profile_set_fingerprint") != self.profile_set_fingerprint:
                raise ValueError
            if policy == "stream_first":
                self._validate_stream_first(transport)
            elif policy == "legacy":
                self._validate_legacy(transport)
            else:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise ValueError("experiment_transport_profile_invalid") from None

    def _validate_stream_first(self, transport: dict[str, Any]) -> None:
        if set(transport) != {"policy", "profile_set_fingerprint", "calls"}:
            raise ValueError
        if not isinstance(transport["calls"], list) or not transport["calls"]:
            raise ValueError
        seen = set()
        for call in transport["calls"]:
            if (
                not isinstance(call, dict)
                or set(call) != {"call_id", "profile_fingerprint"}
                or not isinstance(call["call_id"], str)
                or _IDENTIFIER.fullmatch(call["call_id"]) is None
                or call["call_id"] in seen
                or not isinstance(call["profile_fingerprint"], str)
                or _HASH.fullmatch(call["profile_fingerprint"]) is None
                or call["profile_fingerprint"] not in self.profile_fingerprints
            ):
                raise ValueError
            seen.add(call["call_id"])

    def _validate_legacy(self, transport: dict[str, Any]) -> None:
        if (
            set(transport) != {"policy", "transport", "profile_set_fingerprint", "calls"}
            or transport["transport"] != "nonstream"
            or not isinstance(transport["calls"], list)
            or not transport["calls"]
        ):
            raise ValueError
        seen = set()
        for call in transport["calls"]:
            if not isinstance(call, dict) or set(call) != {
                "call_id",
                "transport",
                "reason",
                "capability_limit",
            }:
                raise ValueError
            if (
                not isinstance(call["call_id"], str)
                or _IDENTIFIER.fullmatch(call["call_id"]) is None
                or call["call_id"] in seen
                or call["transport"] != "nonstream"
            ):
                raise ValueError
            limitation = (call["reason"], call["capability_limit"])
            if limitation == ("provider_profile_unverified", "verified_stream_profiles_empty"):
                if self.profiles:
                    raise ValueError
            elif limitation != (
                "provider_native_tools_unsupported_with_stream",
                "native_tools_require_nonstream",
            ):
                raise ValueError
            seen.add(call["call_id"])

    @staticmethod
    def _trusted_profile(profile: Any) -> bool:
        evidence_kind = profile.evidence_kind
        status = profile.status
        if evidence_kind == "provider_live" or status == "provider_live_verified":
            return any(
                _profile_identity(profile) == _profile_identity(verified)
                for verified in VERIFIED_STREAM_PROFILES
            )
        if evidence_kind != "controlled_test" or status != "controlled_test":
            return False
        endpoint = urlsplit(profile.endpoint)
        return endpoint.scheme == "http" and endpoint.hostname in {
            "127.0.0.1",
            "localhost",
            "::1",
        }


def profile_fingerprint(profile: Any) -> str:
    """Return #124's exact per-profile fingerprint without retaining its fields."""
    return _fingerprint(_profile_identity(profile))


StreamFirstTransportAdapter = ExperimentTransportAdapter
