"""Project persisted solver transport decisions into a safe Job identity."""

from __future__ import annotations

import re
from typing import Any

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_CALL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")
_LEGACY_CAPABILITY_LIMITS = {
    "provider_profile_unverified": "verified_stream_profiles_empty",
    "provider_native_tools_unsupported_with_stream": "native_tools_require_nonstream",
}
TRANSPORT_REJECTION_REASONS = frozenset({
    "provider_profile_unverified", "unknown_endpoint", "stream_adapter_unavailable",
    "provider_native_tools_unsupported_with_stream", "transport_policy_run_mismatch",
    "stream_first_policy_required",
})


def known_transport_rejection(identity: Any) -> bool:
    """Recognize the public refusal schema without treating unknown data as a refusal."""
    rejection = identity.get("rejection") if isinstance(identity, dict) else None
    return (
        isinstance(rejection, dict)
        and set(rejection) == {"call_id", "role", "reason", "new_run_required"}
        and isinstance(rejection["call_id"], str)
        and re.fullmatch(r"solver_call_[0-9a-f]{32}", rejection["call_id"]) is not None
        and isinstance(rejection["role"], str) and _CALL_ID.fullmatch(rejection["role"]) is not None
        and isinstance(rejection["reason"], str) and rejection["reason"] in TRANSPORT_REJECTION_REASONS
        and rejection["new_run_required"] is True
    )


def project_transport_identity(state: Any, job_id: str) -> dict[str, Any] | None:
    """Return only stable transport fields; malformed or incomplete state is unknown."""
    if not isinstance(state, dict) or state.get("run_id") != job_id:
        return None
    locked = state.get("transport_policy")
    calls = state.get("calls")
    if not isinstance(locked, dict) or not isinstance(calls, dict) or not calls:
        return None
    policy = locked.get("policy")
    profile_set = locked.get("profile_set_fingerprint")
    if policy not in {"legacy", "stream_first"} or not _is_hash(profile_set):
        return None

    projected = []
    rejection = None
    seen_call_ids = set()
    from .run_budget import public_solver_call_id

    for internal_call_id, call in calls.items():
        if not isinstance(call, dict):
            return None
        call_id = call.get("role")
        opaque_call_id = public_solver_call_id(job_id, internal_call_id)
        decision = call.get("transport_decision")
        if (
            not isinstance(call_id, str)
            or _CALL_ID.fullmatch(call_id) is None
            or not isinstance(opaque_call_id, str)
            or opaque_call_id in seen_call_ids
            or not isinstance(decision, dict)
            or decision.get("policy") != policy
            or decision.get("profile_set_fingerprint") != profile_set
        ):
            return None
        transport = decision.get("transport")
        evidence_kind = decision.get("evidence_kind")
        if transport == "reject":
            if (
                rejection is not None or call.get("status") != "policy_rejected"
                or decision.get("reason") not in TRANSPORT_REJECTION_REASONS
                or decision.get("new_run_required") is not True
            ):
                return None
            rejection = {
                "call_id": opaque_call_id, "role": call_id,
                "reason": decision["reason"], "new_run_required": True,
            }
            seen_call_ids.add(opaque_call_id)
            continue
        if policy == "stream_first":
            profile = decision.get("profile_fingerprint")
            if (
                transport != "stream"
                or not _is_hash(profile)
                or evidence_kind not in {"controlled_test", "provider_live"}
            ):
                return None
        else:
            capability_limit = _LEGACY_CAPABILITY_LIMITS.get(decision.get("reason"))
            if (
                transport not in {"nonstream", "legacy"}
                or evidence_kind not in {None, "documented"}
                or capability_limit is None
                or decision.get("capability_limit") not in {None, capability_limit}
            ):
                return None

        entry = {
            "call_id": opaque_call_id,
            "role": call_id,
            "policy": policy,
            "transport": transport,
            "evidence_kind": evidence_kind,
        }
        if policy == "stream_first":
            entry["profile_fingerprint"] = profile
        else:
            entry["reason"] = decision.get("reason")
            entry["capability_limit"] = capability_limit
        projected.append(entry)
        seen_call_ids.add(opaque_call_id)

    return {
        "policy": policy,
        "profile_set_fingerprint": profile_set,
        "calls": sorted(projected, key=lambda item: item["call_id"]),
        **({"rejection": rejection} if rejection is not None else {}),
    }


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None
