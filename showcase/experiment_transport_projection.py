"""Project persisted solver transport decisions into a safe Job identity."""

from __future__ import annotations

import re
from typing import Any

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_CALL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")


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
        if policy == "stream_first":
            profile = decision.get("profile_fingerprint")
            if (
                transport != "stream"
                or not _is_hash(profile)
                or evidence_kind not in {"controlled_test", "provider_live"}
            ):
                return None
        elif transport not in {"nonstream", "legacy"}:
            return None
        elif evidence_kind not in {None, "documented"}:
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
            entry["capability_limit"] = decision.get("capability_limit")
        projected.append(entry)
        seen_call_ids.add(opaque_call_id)

    return {
        "policy": policy,
        "profile_set_fingerprint": profile_set,
        "calls": sorted(projected, key=lambda item: item["call_id"]),
    }


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None
