"""Proof artifact grading and explicit formal-attempt lineage."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .experiment_manifest import canonical_json
from .formal_specification import canonical_identity, required_review_fields

STATUSES = frozenset(
    {
        "solved", "partial", "failed", "timeout", "error", "unavailable",
        "unsupported", "unknown", "disabled",
    }
)
DEFAULT_ALLOWED_AXIOMS = frozenset({"propext", "Classical.choice", "Quot.sound"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_INDEPENDENT_TYPES = frozenset({"human", "independent_service"})


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}_identity_invalid")
    return value.strip()


def replace_record(record: ReviewRecord, **changes: Any) -> ReviewRecord:
    return ReviewRecord(**{**record.__dict__, **changes})


@dataclass(frozen=True)
class ReviewRecord:
    review_id: str
    reviewer_authority_id: str
    reviewer_type: str
    problem_hash: str
    spec_hash: str
    target_hash: str
    environment_hash: str
    attempt_hash: str
    approved: bool
    field_results: Mapping[str, bool]
    record_hash: str
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.__dict__, ensure_ascii=False))

    def identity_payload(self) -> dict[str, Any]:
        return {key: value for key, value in self.__dict__.items() if key != "signature"}


@dataclass(frozen=True)
class AuthorityRegistration:
    reviewer_type: str


class ReviewAuthority:
    """Server-controlled independent-review issuer; self-asserted booleans are ignored."""

    def __init__(self, secrets: Mapping[str, str],
                 allowed_authorities: Mapping[str, Any]) -> None:
        self._secrets = dict(secrets)
        self._registrations: dict[str, AuthorityRegistration] = {}
        for authority_id, value in allowed_authorities.items():
            reviewer_type = value.get("type") if isinstance(value, Mapping) else value
            if reviewer_type not in _INDEPENDENT_TYPES:
                raise ValueError("review_authority_not_independent")
            self._registrations[str(authority_id)] = AuthorityRegistration(reviewer_type)
        if not self._secrets:
            raise ValueError("review_authority_unconfigured")
        if set(self._secrets) != set(self._registrations):
            raise ValueError("review_authority_registration_mismatch")

    def _signature(self, payload: Mapping[str, Any], authority_id: str) -> str:
        secret = self._secrets[authority_id].encode("utf-8")
        return hmac.new(secret, canonical_json(payload), hashlib.sha256).hexdigest()

    def issue(self, value: Mapping[str, Any]) -> ReviewRecord:
        authority_id = _identity(value.get("reviewer_authority_id"), "reviewer_authority")
        registration = self._registrations.get(authority_id)
        if registration is None:
            raise ValueError("review_authority_invalid")
        if value.get("reviewer_type") != registration.reviewer_type:
            raise ValueError("review_authority_type_mismatch")
        if registration.reviewer_type not in _INDEPENDENT_TYPES:
            raise ValueError("independent_review_required")
        fields = value.get("field_results")
        required = required_review_fields()
        if (
            not isinstance(fields, Mapping)
            or set(fields) != required
            or any(fields.get(name) is not True for name in required)
        ):
            raise ValueError("review_fields_incomplete")
        identities = ("problem_hash", "spec_hash", "target_hash", "environment_hash",
                      "attempt_hash")
        record = ReviewRecord(
            review_id=_identity(value.get("review_id"), "review"),
            reviewer_authority_id=authority_id,
            reviewer_type=registration.reviewer_type,
            **{name: _identity(value.get(name), name) for name in identities},
            approved=value.get("approved") is True,
            field_results={name: True for name in required},
            record_hash="",
            signature="",
        )
        payload = record.identity_payload()
        record = replace_record(record, record_hash=_hash(payload))
        signed_payload = record.identity_payload()
        return replace_record(record, signature=self._signature(signed_payload, authority_id))


    def verify(self, value: Any) -> ReviewRecord | None:
        if not isinstance(value, Mapping):
            return None
        try:
            if not isinstance(value.get("field_results"), Mapping):
                return None
            issued = self.issue(value)
            supplied_signature = _identity(value.get("signature"), "review_signature")
            if not hmac.compare_digest(issued.signature, supplied_signature):
                return None
            if issued.record_hash != value.get("record_hash"):
                return None
            return issued
        except (KeyError, TypeError, ValueError):
            return None


@dataclass(frozen=True)
class ProofArtifact:
    status: str
    kernel_exit: int | None
    accepted: bool
    cleanup_verified: bool
    environment_hash: str | None
    target_hash: str
    source_hash: str
    proof_hash: str
    print_axioms_raw: str
    print_proof_raw: str
    axioms: list[str] = field(default_factory=list)
    dependency_audit: Mapping[str, Any] = field(default_factory=dict)
    logs: Mapping[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(
            self.__dict__, ensure_ascii=False,
            default=lambda item: dict(item) if isinstance(item, Mapping) else item,
        ))

    def grade(
        self,
        *,
        allowed_axioms: set[str] | frozenset[str] = DEFAULT_ALLOWED_AXIOMS,
        trusted_environment_hash: str | None = None,
        review: Mapping[str, Any] | None = None,
        review_authority: ReviewAuthority | None = None,
        identity: Mapping[str, Any] | None = None,
    ) -> str | None:
        if self.environment_hash != trusted_environment_hash and trusted_environment_hash is not None:
            return None
        if (
            self.status != "solved"
            or self.kernel_exit != 0
            or self.accepted is not True
            or self.cleanup_verified is not True
            or not self.environment_hash
            or trusted_environment_hash is None
            or not hmac.compare_digest(self.environment_hash, trusted_environment_hash)
            or not _SHA256.fullmatch(self.target_hash)
            or not _SHA256.fullmatch(self.source_hash)
            or not _SHA256.fullmatch(self.proof_hash)
            or "#print axioms polynomial_identity" not in self.print_axioms_raw
            or "theorem polynomial_identity" not in self.print_proof_raw
            or "..." in self.print_proof_raw or "⋯" in self.print_proof_raw
            or self.logs.get("truncated") is True
            or self.dependency_audit.get("recursive") is not True
            or self.dependency_audit.get("passed") is not True
            or set(self.axioms) - set(allowed_axioms)
            or "sorryAx" in self.axioms
        ):
            return None
        if not review or review_authority is None or not identity:
            return "L2"
        verified = review_authority.verify(review)
        if verified is None or not verified.approved:
            return "L2"
        for name in ("problem_hash", "spec_hash", "target_hash", "environment_hash",
                     "attempt_hash"):
            if identity.get(name) != getattr(verified, name):
                return "L2"
        if set(verified.field_results) != required_review_fields() or not all(
            verified.field_results.values()
        ):
            return "L2"
        return "L3"


def serialize_attempt_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("formal_result_invalid")
    result = json.loads(json.dumps(value, ensure_ascii=False, default=str))
    status = result.get("status")
    if status not in STATUSES:
        status = "unknown"
    cost = dict(result.get("cost") or {})
    cost.setdefault("elapsed_seconds", 0.0)
    cost.setdefault("output_bytes", 0)
    cost.setdefault("usage", {})
    lineage = dict(result.get("lineage") or {})
    lineage.setdefault("parent_attempt_id", result.get("parent_attempt_id"))
    grade = result.get("grade")
    if status != "solved" or grade not in {"L2", "L3"}:
        grade = None
    result.update(status=status, grade=grade, cost=cost, lineage=lineage)
    result.setdefault("schema_version", 1)
    result.setdefault("reason", None)
    result.setdefault("specifications", {})
    result.setdefault("proof_artifact", None)
    return result


def create_attempt(value: Mapping[str, Any], *, attempt_id: str,
                   backend: str | None = None) -> dict[str, Any]:
    parent = value.get("attempt_id") if value.get("attempt_id") else None
    attempt_id = _identity(attempt_id, "attempt")
    if attempt_id == parent:
        raise ValueError("attempt_identity_reused")
    request = json.loads(json.dumps(value, ensure_ascii=False))
    if request.get("status"):
        old_cost = dict(request.get("cost") or {})
        lineage_cost = dict(old_cost.get("lineage") or {})
        lineage_cost["elapsed_seconds"] = float(
            lineage_cost.get("elapsed_seconds", 0)
        ) + float(old_cost.get("elapsed_seconds", 0))
        lineage_cost["output_bytes"] = int(
            lineage_cost.get("output_bytes", 0)
        ) + int(old_cost.get("output_bytes", 0))
        lineage_cost["unknown"] = bool(
            lineage_cost.get("unknown") or old_cost.get("unknown")
            or request.get("status") == "unknown"
        )
        lineage_cost["attempts"] = list(lineage_cost.get("attempts") or []) + [parent]
        request["cost"] = {
            "elapsed_seconds": 0.0, "output_bytes": 0,
            "unknown": False, "lineage": lineage_cost,
        }
    else:
        request["cost"] = {"elapsed_seconds": 0.0, "output_bytes": 0, "lineage": {}}
    request.update(attempt_id=attempt_id, parent_attempt_id=parent)
    if backend is not None:
        request.setdefault("policy", {})["backend"] = _identity(backend, "backend")
    request["deadline"] = value.get("deadline")
    return request


def finalize_attempt(value: Mapping[str, Any], *, status: str, reason: str | None,
                     cost: Mapping[str, Any] | None = None) -> dict[str, Any]:
    result = dict(value)
    result["status"] = status if status in STATUSES else "unknown"
    result["reason"] = reason
    result["cost"] = dict(cost or {})
    result["lineage"] = {"parent_attempt_id": value.get("parent_attempt_id")}
    return result


def attempt_hash(value: Mapping[str, Any]) -> str:
    stable = {
        key: value.get(key)
        for key in ("job_id", "run_id", "attempt_id", "parent_attempt_id", "target")
    }
    return canonical_identity(stable)


__all__ = [
    "AuthorityRegistration", "DEFAULT_ALLOWED_AXIOMS", "ProofArtifact", "ReviewAuthority",
    "ReviewRecord", "STATUSES", "attempt_hash", "create_attempt", "finalize_attempt",
    "serialize_attempt_result",
]
