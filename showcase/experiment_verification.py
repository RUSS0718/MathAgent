"""Independent, read-only verification and allowlisted report export for Runs."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .experiment_execution_state import load_registered_manifest
from .experiment_manifest import canonical_json, manifest_digest
from .experiment_runner import read_status
from .experiment_verification_checks import _verify_job
from .experiment_verification_reporting import (
    _evidence_hashes,
    _evidence_matches_previous_report,
    _existing_evidence_matches,
    _write_evidence,
    _write_verification,
    export_experiment_report,
)
from .experiment_verification_state import (
    _CHECKS,
    _STOP_REASONS,
    _aggregate_usage_mismatch,
    _check,
    _combine,
    _consistent_applied_config,
    _coverage_check,
    _execution_mode,
    _index_records,
    _overall_status,
    _read_job_evidence,
    _sum_budgets,
    _valid_run_record,
)

__all__ = ["export_experiment_report", "verify_experiment_run"]


def verify_experiment_run(
    run_id: str,
    *,
    output_root: str | Path,
    read_client: Any,
) -> dict[str, Any]:
    """Reconcile one saved registration with public GET-only Job evidence."""
    directory = Path(output_root) / run_id
    status = read_status(run_id, output_root=output_root)
    manifest = load_registered_manifest(directory)
    digest = manifest_digest(manifest)
    if status.get("manifest_sha256") != digest:
        raise ValueError("experiment_manifest_hash_mismatch")

    records, integrity_failures = _index_records(status.get("run_records"))
    samples = manifest["samples"]
    completed = status.get("completed_samples", [])
    if (
        not isinstance(completed, list)
        or any(type(index) is not int or index < 0 or index >= len(samples) for index in completed)
        or len(completed) != len(set(completed))
    ):
        integrity_failures.append("completed_samples_invalid")
        completed = []
    if status.get("total") != len(samples) or status.get("completed") != len(completed):
        integrity_failures.append("completion_count_mismatch")
    if status.get("phase") == "completed" and (
        completed != list(range(len(samples))) or set(records) != {item["id"] for item in samples}
    ):
        integrity_failures.append("completed_run_incomplete")
    if status.get("stop_reason") is not None and (
        not isinstance(status.get("stop_reason"), str)
        or status["stop_reason"] not in _STOP_REASONS
    ):
        integrity_failures.append("stop_reason_invalid")

    directory_has_intent = (directory / "dispatch_intent.json").exists()
    per_sample: list[dict[str, dict[str, Any]]] = []
    archived_evidence: list[dict[str, Any]] = []
    observed_budgets: dict[str, dict[str, Any]] = {}
    evidence_complete = True
    for index, sample in enumerate(samples):
        record = records.get(sample["id"])
        if record is None:
            outcome = {name: _check("NOT_RUN", "sample_not_dispatched") for name in _CHECKS}
            if directory_has_intent:
                outcome = {
                    name: _check("UNKNOWN", "dispatch_intent_unresolved") for name in _CHECKS
                }
            per_sample.append(outcome)
            continue
        if not _valid_run_record(record, sample, index, completed):
            per_sample.append({name: _check("FAIL", "run_record_mismatch") for name in _CHECKS})
            integrity_failures.append("run_record_mismatch")
            evidence_complete = False
            continue
        remote = _read_job_evidence(read_client, record)
        if remote.get("status") != "PASS":
            evidence_complete = False
            outcome = {
                name: _check("UNKNOWN", remote.get("reason", "job_evidence_unavailable"))
                for name in _CHECKS
            }
            if remote.get("status") == "FAIL":
                outcome = {
                    name: _check("FAIL", remote.get("reason", "job_identity_mismatch"))
                    for name in _CHECKS
                }
            per_sample.append(outcome)
            continue
        job, report, evidence, lookup = (
            remote[name] for name in ("job", "report", "evidence", "lookup")
        )
        job_checks, safe_evidence, budget = _verify_job(
            manifest, sample, record, job, report, evidence, lookup
        )
        per_sample.append(job_checks)
        observed_budgets[sample["id"]] = budget
        archived_evidence.append(safe_evidence)

    checks = {name: _combine([item[name] for item in per_sample]) for name in _CHECKS}
    archived_hashes = _evidence_hashes(directory) if not evidence_complete else None
    archive_matches = (
        _existing_evidence_matches(directory, archived_evidence)
        if evidence_complete
        else archived_hashes is not None
        and _evidence_matches_previous_report(directory, archived_hashes)
    )
    if not archive_matches:
        integrity_failures.append("archived_evidence_mismatch")
    if integrity_failures:
        for name in _CHECKS:
            checks[name] = _check("FAIL", "persisted_state_inconsistent")
    checks["coverage"] = _coverage_check(
        status, manifest, records, completed, directory_has_intent, integrity_failures, per_sample
    )
    usage_error = _aggregate_usage_mismatch(status, samples, records, completed, observed_budgets)
    if usage_error:
        checks["usage"] = _check("FAIL", usage_error)

    report = {
        "schema_version": 1,
        "run_id": run_id,
        "manifest_id": manifest["manifest_id"],
        "manifest_sha256": digest,
        "evidence_kind": manifest["evidence_kind"],
        "source_identity": manifest["source_identity"],
        "model_conditions": manifest["model"],
        "applied_config": _consistent_applied_config(archived_evidence),
        "transport_policy": manifest["transport"],
        "sample_ids": [sample["id"] for sample in samples],
        "samples": [
            {
                key: sample[key]
                for key in ("id", "type", "input_sha256", "text_sha256")
            }
            for sample in samples
        ],
        "evidence_sha256": (
            sorted(hashlib.sha256(canonical_json(item)).hexdigest() for item in archived_evidence)
            if evidence_complete
            else archived_hashes or []
        ),
        "budget": {
            "run_limits": manifest["run_limits"],
            "batch_limits": manifest["batch_limits"],
            "observed": _sum_budgets(observed_budgets.values()),
        },
        "stop_reason": status.get("stop_reason")
        if isinstance(status.get("stop_reason"), str)
        and status["stop_reason"] in _STOP_REASONS
        else None,
        "execution_mode": _execution_mode(archived_evidence),
        "checks": checks,
        "status": _overall_status(checks, usage_policy=manifest.get("usage_policy", "required")),
    }
    if archive_matches:
        if evidence_complete:
            _write_evidence(directory, archived_evidence)
        _write_verification(directory, report)
    return report
