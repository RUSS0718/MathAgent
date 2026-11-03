"""Frozen single-factor pair registration and fail-closed admission."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .experiment_execution_state import save_execution_status, write_json_once
from .experiment_manifest import canonical_json, manifest_digest, validate_manifest
from .solver_harness.paired_conditions import STRATEGIES

_PAIR_KEYS = {
    "schema_version",
    "pair_id",
    "readiness_report_sha256",
    "factor",
    "baseline",
    "variant",
}
_ARM_KEYS = {"run_id", "manifest", "features"}
_FEATURE_KEYS = set(STRATEGIES)
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def load_pair_manifest(path: str | Path) -> dict[str, Any]:
    """Load a strict pair registration without opening reserved or sensitive paths."""
    from .experiment_sources import _read_control_json

    value = _read_control_json(path, "experiment_pair_manifest_invalid")
    return validate_pair_manifest(value)


def load_readiness_report(path: str | Path) -> dict[str, Any]:
    """Load an untrusted readiness report; only an independent verifier can admit it."""
    from .experiment_sources import _read_control_json

    value = _read_control_json(path, "experiment_readiness_report_invalid")
    if not isinstance(value, dict):
        raise ValueError("experiment_readiness_report_invalid")
    canonical_json(value)
    return value


def validate_pair_manifest(value: Any) -> dict[str, Any]:
    """Validate that registered arms vary in exactly one approved component flag."""
    if not isinstance(value, dict) or set(value) != _PAIR_KEYS:
        raise ValueError("experiment_pair_manifest_invalid")
    try:
        if type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError
        if not isinstance(value["pair_id"], str) or not _IDENTIFIER.fullmatch(value["pair_id"]):
            raise ValueError
        if value["factor"] not in STRATEGIES:
            raise ValueError
        if not _is_hash(value["readiness_report_sha256"]):
            raise ValueError
        arms = {}
        for name in ("baseline", "variant"):
            arm = value[name]
            if not isinstance(arm, dict) or set(arm) != _ARM_KEYS:
                raise ValueError
            if not isinstance(arm["run_id"], str) or not _IDENTIFIER.fullmatch(arm["run_id"]):
                raise ValueError
            features = arm["features"]
            if (
                not isinstance(features, dict)
                or set(features) != _FEATURE_KEYS
                or any(type(enabled) is not bool for enabled in features.values())
            ):
                raise ValueError
            arms[name] = {
                "run_id": arm["run_id"],
                "manifest": validate_manifest(arm["manifest"]),
                "features": features,
            }
        if len({value["pair_id"], *(arm["run_id"] for arm in arms.values())}) != 3:
            raise ValueError
        baseline, variant = arms["baseline"], arms["variant"]
        if not _only_factor_differs(baseline, variant, value["factor"]):
            raise ValueError
        if baseline["manifest"]["evidence_kind"] != variant["manifest"]["evidence_kind"]:
            raise ValueError
        if any(arm["manifest"]["model"]["verification_mode"] == "off" for arm in arms.values()):
            raise ValueError
        canonical_json(value)
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError("experiment_pair_manifest_invalid") from None
    return value


def pair_manifest_digest(value: dict[str, Any]) -> str:
    """Return the canonical digest bound by pair registration and CLI authorization."""
    return hashlib.sha256(canonical_json(value)).hexdigest()


def run_pair(
    pair: Any,
    *,
    expected_sha256: str,
    readiness_report: Any,
    output_root: str | Path,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Persist a NOT_RUN result until aggregate readiness and component Job wiring exist."""
    registration = validate_pair_manifest(pair)
    digest = pair_manifest_digest(registration)
    authorization = context.get("authorization")
    try:
        authorized = authorization.authorize(
            digest, registration["baseline"]["manifest"]["evidence_kind"], registration["pair_id"]
        )
    except Exception:
        authorized = False
    if not authorized:
        raise ValueError("experiment_invocation_authorization_required")

    reason = _admission_blocker(registration, expected_sha256, readiness_report)
    directory = Path(output_root) / "pairs" / registration["pair_id"]
    try:
        directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise ValueError("experiment_pair_exists") from None
    write_json_once(directory / "registration.json", registration)
    state = {
        "schema_version": 1,
        "pair_id": registration["pair_id"],
        "pair_sha256": digest,
        "factor": registration["factor"],
        "status": "NOT_RUN",
        "phase": "readiness_blocked",
        "execution_order": [],
        "completed": 0,
        "total": 2,
        "dispatch_count": 0,
        "execution_blockers": [
            "aggregate_readiness_verifier_unavailable",
            "component_job_path_unavailable",
        ],
        "stop_reason": reason,
        "readiness": {"issue_number": 127, "status": "NOT_RUN"},
        "arms": {
            name: {
                "run_id": registration[name]["run_id"],
                "manifest_sha256": manifest_digest(registration[name]["manifest"]),
                "status": "not_started",
                "verification_status": "NOT_RUN",
            }
            for name in ("baseline", "variant")
        },
    }
    save_execution_status(directory, state)
    return state


def _admission_blocker(pair: dict[str, Any], expected_sha256: str, report: Any) -> str:
    """Return the first fail-closed admission reason without trusting report status."""
    if not _is_hash(expected_sha256) or expected_sha256 != pair_manifest_digest(pair):
        return "experiment_pair_manifest_hash_mismatch"
    if not isinstance(report, dict):
        return "experiment_readiness_not_run"
    try:
        report_hash = hashlib.sha256(canonical_json(report)).hexdigest()
    except (TypeError, ValueError, OverflowError):
        return "experiment_readiness_mismatch"
    if report_hash != pair["readiness_report_sha256"]:
        return "experiment_readiness_mismatch"
    if report.get("status") != "PASS":
        return "experiment_readiness_not_passed"
    return "experiment_readiness_aggregate_verifier_unavailable"


def _only_factor_differs(
    baseline: dict[str, Any], variant: dict[str, Any], factor: str
) -> bool:
    """Compare frozen manifests and registered component flags independently."""
    left = json.loads(canonical_json(baseline["manifest"]))
    right = json.loads(canonical_json(variant["manifest"]))
    left.pop("manifest_id")
    right.pop("manifest_id")
    left["authorization"].pop("scope")
    right["authorization"].pop("scope")
    if left != right:
        return False
    left_features, right_features = baseline["features"], variant["features"]
    return (
        left_features[factor] != right_features[factor]
        and {key: value for key, value in left_features.items() if key != factor}
        == {key: value for key, value in right_features.items() if key != factor}
    )


def _is_hash(value: Any) -> bool:
    """Return whether a value is a lowercase SHA-256 digest."""
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None
