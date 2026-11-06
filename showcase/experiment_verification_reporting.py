"""Create and persist allowlisted experiment verification reports."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .experiment_execution_state import load_registered_manifest
from .experiment_manifest import canonical_json, manifest_digest
from .experiment_verification_state import _CHECKS, _STOP_REASONS, _finite_number, _overall_status

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")
_PUBLIC_CALL_ID = re.compile(r"solver_call_[0-9a-f]{32}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_FINISH_REASONS = {"stop", "length", "tool_calls", "function_call", "content_filter"}
_EXECUTION_MODES = {"live", "fake", "replay", "experimental", "unavailable", "planned"}


def _safe_choice(value: Any, choices: set[str], fallback: str) -> str:
    """Return a fixed categorical value without trusting arbitrary remote text."""
    return value if isinstance(value, str) and value in choices else fallback


def _safe_evidence(
    sample: dict[str, Any],
    record: dict[str, Any],
    job: dict[str, Any],
    report: dict[str, Any],
    evidence: dict[str, Any],
    attempts: Any,
    budget: Any,
    expected_model: str,
    allowed_roles: set[str],
    manifest_evidence_kind: str,
) -> dict[str, Any]:
    """Project public API responses into a report with no answer or prompt text."""
    projected_attempts = []
    for item in attempts if isinstance(attempts, list) else []:
        if not isinstance(item, dict):
            continue
        projection = {
            "attempt_index": item.get("attempt_index")
            if type(item.get("attempt_index")) is int and item["attempt_index"] > 0
            else None,
            "status": _safe_choice(
                item.get("status"),
                {"success", "error", "unknown", "not_submitted", "pending", "reserved"},
                "unavailable",
            ),
            "dispatch_status": _safe_choice(
                item.get("dispatch_status"),
                {"transport_observed", "not_submitted", "reserved_dispatch_unconfirmed"},
                "unavailable",
            ),
            "finish_reason": _safe_choice(item.get("finish_reason"), _FINISH_REASONS, "unavailable"),
            "requested_model": expected_model
            if item.get("requested_model") == expected_model
            else "mismatch",
            "usage": _safe_attempt_usage(item.get("usage")),
            "thinking_mode": item.get("thinking_mode")
            if type(item.get("thinking_mode")) is bool
            else None,
            "temperature": item.get("temperature")
            if _finite_number(item.get("temperature"))
            else None,
            "max_tokens": item.get("max_tokens")
            if type(item.get("max_tokens")) is int and item["max_tokens"] > 0
            else None,
            "requests_timeout_seconds": item.get("requests_timeout_seconds")
            if type(item.get("requests_timeout_seconds")) is int
            and item["requests_timeout_seconds"] > 0
            else None,
            "effective_timeout_seconds": item.get("effective_timeout_seconds")
            if _finite_number(item.get("effective_timeout_seconds"))
            and item["effective_timeout_seconds"] > 0
            else None,
            "retry_limit": item.get("retry_limit")
            if type(item.get("retry_limit")) is int and item["retry_limit"] >= 0
            else None,
        }
        for key in ("attempt_id", "logical_call_id"):
            value = item.get(key)
            if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,100}", value):
                projection[key] = value
        if item.get("run_id") == record.get("job_id"):
            projection["run_id"] = record["job_id"]
        if isinstance(item.get("role"), str) and item["role"] in allowed_roles:
            projection["role"] = item["role"]
        if isinstance(item.get("solver_call_id"), str) and _PUBLIC_CALL_ID.fullmatch(
            item["solver_call_id"]
        ) is not None:
            projection["solver_call_id"] = item["solver_call_id"]
        projected_attempts.append(
            projection
        )
    verification = (
        evidence.get("verification") if isinstance(evidence.get("verification"), dict) else {}
    )
    history = verification.get("history") if isinstance(verification.get("history"), list) else []
    latest = history[-1] if history and isinstance(history[-1], dict) else {}
    source = latest.get("source") if isinstance(latest.get("source"), dict) else {}
    semantic = evidence.get("semantics") if isinstance(evidence.get("semantics"), dict) else {}
    artifact = latest.get("artifact") if isinstance(latest.get("artifact"), dict) else {}
    job_result = job.get("result") if isinstance(job.get("result"), dict) else {}
    report_body = report.get("report") if isinstance(report.get("report"), dict) else {}
    solver_evidence = evidence.get("solver")
    solver_evidence_kind = (
        solver_evidence.get("evidence_kind")
        if isinstance(solver_evidence, dict)
        else None
    )
    execution_mode = (
        "live"
        if manifest_evidence_kind == "provider_live" and solver_evidence_kind == "live"
        else _safe_choice(
            solver_evidence_kind,
            {"scripted", "fault_injection"}
            if manifest_evidence_kind != "provider_live"
            else set(),
            "unavailable",
        )
    )
    return {
        "sample_id": sample["id"],
        "job_id": record.get("job_id"),
        "job_status": _safe_choice(
            job.get("status"), {"queued", "running", "succeeded", "failed", "canceled"}, "unknown"
        ),
        "execution_mode": execution_mode,
        "request_attempts": projected_attempts,
        "tools": _safe_tool_summaries(report_body.get("tool_summaries")),
        "budget": _safe_budget(budget),
        "solver_mode": _safe_choice(
            job_result.get("solver_mode"), {"star_reference"}, "unavailable"
        ),
        "semantics": {
            "execution": _safe_choice(
                semantic.get("execution"),
                {"queued", "running", "waiting_input", "completed", "needs_review", "failed", "canceled"},
                "unknown",
            ),
            "transport": _safe_choice(
                semantic.get("transport"), {"known", "unknown", "pending", "unavailable"}, "unknown"
            ),
            "whole_review": _safe_choice(
                semantic.get("whole_review"), {"accepted", "rejected", "not_reviewed"}, "unknown"
            ),
            "binding": _safe_choice(
                semantic.get("binding"), {"same_artifact", "artifact_changed", "unbound"}, "unknown"
            ),
            "formal_verification": _safe_choice(
                semantic.get("formal_verification"), {"not_verified"}, "unknown"
            ),
            "verification_requirement": _safe_choice(
                semantic.get("verification_requirement"), {"default", "required_unmet"}, "unknown"
            ),
        },
        "whole_review": {
            "scope": latest.get("scope") if latest.get("scope") == "whole_solution_llm_review" else "unavailable",
            "checker_version": latest.get("checker_version") if latest.get("checker_version") == "star-whole-review-v1" else "unavailable",
            "accepted": latest.get("scope") == "whole_solution_llm_review"
            and latest.get("checker_version") == "star-whole-review-v1"
            and isinstance(latest.get("findings"), list)
            and any(tag in latest["findings"]
                    for tag in ("llm_whole_review_accept", "llm_whole_review_accepted")),
            "binding": _safe_choice(
                verification.get("binding"), {"same_artifact", "artifact_changed", "unbound"}, "unknown"
            ),
            "artifact_sha256": (
                artifact.get("sha256")
                if isinstance(artifact.get("sha256"), str)
                and _SHA256.fullmatch(artifact["sha256"])
                else None
            ),
            "source": {
                "run_id": record["job_id"] if source.get("run_id") == record["job_id"] else None,
                "plan_version": _safe_nonnegative_int(source.get("plan_version")),
                "attempt_index": _safe_nonnegative_int(source.get("attempt_index")),
                "state_revision": _safe_nonnegative_int(source.get("state_revision")),
                "origin": source.get("origin")
                if isinstance(source.get("origin"), str) and source["origin"] in allowed_roles
                else None,
                "candidate_version": _safe_nonnegative_int(source.get("candidate_version")),
            },
        },
        "transport_identity": _safe_transport(
            evidence.get("solver", {}).get("transport_identity")
            if isinstance(evidence.get("solver"), dict)
            else None
        ),
        "applied_config": None,
    }


def _safe_tool_summaries(values: Any) -> list[dict[str, Any]]:
    """Keep only categorical tool outcomes and numeric duration in pair evidence."""
    if not isinstance(values, list):
        return []
    output = []
    for item in values:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        status = item.get("status")
        error = item.get("error_category")
        output.append({
            "name": name if isinstance(name, str) and _IDENTIFIER.fullmatch(name) else None,
            "status": status if status in {"completed", "failed", "unknown", "rejected"} else "unknown",
            "duration_seconds": item.get("duration_seconds")
            if _finite_number(item.get("duration_seconds")) and item["duration_seconds"] >= 0
            else None,
            "error_category": error
            if isinstance(error, str) and _IDENTIFIER.fullmatch(error)
            else None,
        })
    return output


def _safe_attempt_usage(value: Any) -> dict[str, int | None] | None:
    """Keep only the three nonnegative provider usage counters."""
    if not isinstance(value, dict):
        return None
    return {
        key: value.get(key) if type(value.get(key)) is int and value[key] >= 0 else None
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }


def _safe_nonnegative_int(value: Any) -> int | None:
    """Retain only a nonnegative integer from a public projection."""
    return value if type(value) is int and value >= 0 else None


def _safe_budget(value: Any) -> dict[str, Any] | None:
    """Retain only numeric and categorical ledger fields for the archive."""
    if not isinstance(value, dict):
        return None
    keys = (
        "logical_calls",
        "http_attempts",
        "tool_calls",
        "provider_known",
        "provider_unknown_fields",
        "reserved_tokens",
        "charged_tokens",
        "unknown_attempts",
        "unresolved_attempts",
        "unknown_tool_calls",
        "deadline_at",
        "wall_time_seconds",
        "cost",
    )
    budget = {key: value.get(key) for key in keys}
    raw_limits = value.get("limits")
    limit_names = {
        "max_model_calls", "max_http_attempts", "max_tool_calls", "max_tokens", "max_runtime_seconds"
    }
    budget["limits"] = (
        {
            key: amount
            if (type(amount) is int and amount > 0)
            or (key == "max_runtime_seconds" and _finite_number(amount) and amount > 0)
            else None
            for key, amount in raw_limits.items()
            if key in limit_names
        }
        if isinstance(raw_limits, dict)
        else None
    )
    for key in (
        "logical_calls",
        "http_attempts",
        "tool_calls",
        "reserved_tokens",
        "charged_tokens",
        "unknown_attempts",
        "unresolved_attempts",
        "unknown_tool_calls",
    ):
        if type(budget[key]) is not int or budget[key] < 0:
            budget[key] = None
    for key in ("deadline_at", "wall_time_seconds", "cost"):
        number = budget[key]
        if number is None and key == "cost":
            continue
        if not _finite_number(number):
            budget[key] = None
        elif (key == "deadline_at" and number <= 0) or (
            key in {"wall_time_seconds", "cost"} and number < 0
        ):
            budget[key] = None
    for key in ("provider_known", "provider_unknown_fields"):
        counters = budget[key]
        budget[key] = (
            {
                name: amount if type(amount) is int and amount >= 0 else None
                for name, amount in counters.items()
                if name in {"prompt_tokens", "completion_tokens", "total_tokens"}
            }
            if isinstance(counters, dict)
            else None
        )
    return budget


def _safe_transport(value: Any) -> dict[str, Any] | None:
    """Keep transport identity fields, excluding arbitrary provider payloads."""
    policy = value.get("policy") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or not isinstance(policy, str)
        or policy not in {"legacy", "stream_first"}
        or not isinstance(value.get("profile_set_fingerprint"), str)
        or _SHA256.fullmatch(value["profile_set_fingerprint"]) is None
        or not isinstance(value.get("calls"), list)
    ):
        return None
    calls = []
    for call in value["calls"]:
        evidence_kind = call.get("evidence_kind") if isinstance(call, dict) else None
        transport = call.get("transport") if isinstance(call, dict) else None
        if (
            not isinstance(call, dict)
            or not isinstance(call.get("call_id"), str)
            or _PUBLIC_CALL_ID.fullmatch(call["call_id"]) is None
            or not isinstance(call.get("role"), str)
            or _IDENTIFIER.fullmatch(call["role"]) is None
            or call.get("policy") != value["policy"]
            or not isinstance(transport, str)
            or transport not in {"stream", "nonstream", "legacy"}
            or (evidence_kind is not None and not isinstance(evidence_kind, str))
            or evidence_kind
            not in (
                {None, "documented"}
                if value["policy"] == "legacy"
                else {"documented", "controlled_test", "provider_live"}
            )
            or (
                call.get("profile_fingerprint") is not None
                and (
                    not isinstance(call["profile_fingerprint"], str)
                    or _SHA256.fullmatch(call["profile_fingerprint"]) is None
                )
            )
            or any(
                call.get(key) is not None
                and (
                    not isinstance(call[key], str)
                    or _IDENTIFIER.fullmatch(call[key]) is None
                )
                for key in ("reason", "capability_limit")
            )
        ):
            return None
        calls.append(
            {
                key: call.get(key)
                for key in (
                    "call_id",
                    "role",
                    "policy",
                    "transport",
                    "evidence_kind",
                    "profile_fingerprint",
                    "reason",
                    "capability_limit",
                )
            }
        )
    return {
        "policy": value.get("policy"),
        "profile_set_fingerprint": value.get("profile_set_fingerprint"),
        "calls": calls,
    }


def export_experiment_report(
    run_id: str,
    *,
    output_root: str | Path,
    output: str | Path,
) -> dict[str, Any]:
    """Export the last verified allowlisted report without contacting the server."""
    directory = Path(output_root) / run_id
    report_path = directory / "verification.json"
    digest_path = directory / "verification.sha256"
    try:
        content = report_path.read_bytes()
        expected = digest_path.read_text(encoding="ascii").strip()
        report = json.loads(content)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("experiment_verification_unavailable") from None
    expected_fields = {
        "schema_version", "run_id", "manifest_id", "manifest_sha256", "evidence_kind",
        "source_identity", "model_conditions", "applied_config", "transport_policy",
        "sample_ids", "samples", "evidence_sha256", "budget", "stop_reason",
        "execution_mode", "checks", "process_coverage", "status",
    }
    legacy_fields = expected_fields - {"process_coverage"}
    legacy_checks = ("transport", "task", "usage", "coverage")
    is_legacy = isinstance(report, dict) and report.get("schema_version") == 1 and set(report) == legacy_fields
    is_current = isinstance(report, dict) and report.get("schema_version") == 2 and set(report) == expected_fields
    expected_checks = legacy_checks if is_legacy else _CHECKS
    process_coverage = report.get("process_coverage") if isinstance(report, dict) else None
    process_coverage_invalid = not is_legacy and (
        not isinstance(process_coverage, dict)
        or set(process_coverage)
        != {
            "registered", "audited", "completed_without_plan", "planned", "path_completed",
            "not_observed", "incomplete", "not_provider_live", "unknown", "not_run", "failed",
        }
        or any(
            type(value) is not int or value < 0
            for value in process_coverage.values()
        )
        or process_coverage.get("audited", 0) > process_coverage.get("registered", 0)
        or process_coverage.get("path_completed", 0) > process_coverage.get("planned", 0)
        or process_coverage.get("planned", 0) > process_coverage.get("registered", 0)
        or process_coverage.get("planned", 0) > process_coverage.get("audited", 0)
        or process_coverage.get("not_provider_live", 0) > process_coverage.get("planned", 0)
        or process_coverage.get("incomplete", 0) > process_coverage.get("planned", 0)
        or sum(
            process_coverage.get(key, 0)
            for key in (
                "path_completed", "not_observed", "incomplete", "not_provider_live", "unknown", "not_run", "failed"
            )
        ) != process_coverage.get("registered", 0)
        or process_coverage.get("completed_without_plan", 0)
        > process_coverage.get("not_observed", 0)
    )
    if (
        not isinstance(report, dict)
        or not (is_legacy or is_current)
        or report.get("run_id") != run_id
        or hashlib.sha256(content).hexdigest() != expected
    ):
        raise ValueError("experiment_verification_invalid")
    try:
        manifest = load_registered_manifest(directory)
        digest = manifest_digest(manifest)
    except (OSError, ValueError, TypeError):
        raise ValueError("experiment_verification_invalid") from None
    expected_samples = [
        {key: sample[key] for key in ("id", "type", "input_sha256", "text_sha256")}
        for sample in manifest["samples"]
    ]
    expected_multistep_count = sum(
        sample["type"] == "multistep" for sample in manifest["samples"]
    )
    registered_process_count = (
        process_coverage.get("registered") if isinstance(process_coverage, dict) else None
    )
    legacy_multistep_report = is_legacy and any(
        sample["type"] == "multistep" for sample in manifest["samples"]
    )
    checks = report.get("checks")
    if (
        report.get("schema_version") != (1 if is_legacy else 2)
        or report.get("manifest_id") != manifest["manifest_id"]
        or report.get("manifest_sha256") != digest
        or report.get("evidence_kind") != manifest["evidence_kind"]
        or report.get("source_identity") != manifest["source_identity"]
        or report.get("model_conditions") != manifest["model"]
        or report.get("status")
        != _overall_status(
            report.get("checks", {}),
            usage_policy=manifest.get("usage_policy", "required"),
            check_names=expected_checks,
        )
        or report.get("transport_policy") != manifest["transport"]
        or report.get("sample_ids") != [sample["id"] for sample in manifest["samples"]]
        or report.get("samples") != expected_samples
        or (not is_legacy and registered_process_count != expected_multistep_count)
        or legacy_multistep_report
        or not isinstance(report.get("evidence_sha256"), list)
        or any(
            not isinstance(value, str) or _SHA256.fullmatch(value) is None
            for value in report["evidence_sha256"]
        )
        or report["evidence_sha256"] != sorted(set(report["evidence_sha256"]))
        or report["evidence_sha256"] != _evidence_hashes(directory)
        or not isinstance(report.get("budget"), dict)
        or set(report["budget"]) != {"run_limits", "batch_limits", "observed"}
        or report["budget"].get("run_limits") != manifest["run_limits"]
        or report["budget"].get("batch_limits") != manifest["batch_limits"]
        or not isinstance(report["budget"].get("observed"), dict)
        or set(report["budget"]["observed"])
        != {"logical_calls", "http_attempts", "tool_calls", "charged_tokens", "wall_seconds"}
        or any(
            not _finite_number(value) or value < 0
            for value in report["budget"]["observed"].values()
        )
        or (report.get("stop_reason") is not None and _safe_choice(report.get("stop_reason"), _STOP_REASONS, "") == "")
        or _safe_choice(report.get("execution_mode"), _EXECUTION_MODES, "") == ""
        or (report.get("applied_config") is not None and report["applied_config"] != manifest["model"])
        or not isinstance(checks, dict)
        or set(checks) != set(expected_checks)
        or any(
            not isinstance(value, dict)
            or set(value) != {"status", "reason"}
            or not isinstance(value.get("status"), str)
            or value["status"] not in {"PASS", "FAIL", "UNKNOWN", "NOT_RUN"}
            or not isinstance(value.get("reason"), str)
            or re.fullmatch(r"[a-z0-9_]{1,80}", value["reason"]) is None
            for value in checks.values()
        )
        or process_coverage_invalid
    ):
        raise ValueError("experiment_verification_invalid")
    try:
        destination = Path(output).resolve()
    except (OSError, RuntimeError):
        raise ValueError("experiment_export_path_invalid") from None
    parts = [part.casefold() for part in destination.parts]
    if (
        parts[-2:] == ["tests", "test.md"]
        or any(part.startswith(".env") for part in parts)
        or any(part in {".git", ".venv", "venv", "node_modules", "__pycache__"} for part in parts)
    ):
        raise ValueError("experiment_export_path_invalid")
    _write_atomic(destination, canonical_json(report), exclusive=True)
    return {
        "run_id": run_id,
        "status": report["status"],
        "sha256": hashlib.sha256(canonical_json(report)).hexdigest(),
        "output": str(destination),
    }


def _write_evidence(directory: Path, values: list[dict[str, Any]]) -> None:
    """Persist each redacted Job projection under its content identity."""
    evidence_dir = directory / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for item in values:
        data = canonical_json(item)
        path = evidence_dir / f"{hashlib.sha256(data).hexdigest()}.json"
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError("experiment_evidence_archive_mismatch")
            continue
        try:
            _write_atomic(path, data, exclusive=True)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ValueError("experiment_evidence_archive_mismatch") from None


def _existing_evidence_matches(directory: Path, values: list[dict[str, Any]]) -> bool:
    """Require existing content-addressed evidence to match the current public snapshot."""
    evidence_dir = directory / "evidence"
    if not evidence_dir.exists():
        report_path = directory / "verification.json"
        digest_path = directory / "verification.sha256"
        if not report_path.exists() and not digest_path.exists():
            return True
        if not report_path.exists() or not digest_path.exists():
            return False
        try:
            previous_content = report_path.read_bytes()
            previous_digest = digest_path.read_text(encoding="ascii").strip()
            previous = json.loads(previous_content)
        except (OSError, UnicodeError, json.JSONDecodeError):
            return False
        if hashlib.sha256(previous_content).hexdigest() != previous_digest:
            return False
        previous_hashes = previous.get("evidence_sha256") if isinstance(previous, dict) else None
        if previous_hashes is None:
            return True
        expected_hashes = sorted(
            hashlib.sha256(canonical_json(item)).hexdigest() for item in values
        )
        return previous_hashes == expected_hashes and not previous_hashes
    if evidence_dir.is_symlink() or not evidence_dir.is_dir():
        return False
    expected = {
        f"{hashlib.sha256(data).hexdigest()}.json": data
        for data in (canonical_json(item) for item in values)
    }
    paths = list(evidence_dir.iterdir())
    if {path.name for path in paths} != set(expected):
        return False
    for path in paths:
        if path.is_symlink() or not path.is_file() or _SHA256.fullmatch(path.stem) is None:
            return False
        try:
            content = path.read_bytes()
        except OSError:
            return False
        if content != expected[path.name] or hashlib.sha256(content).hexdigest() != path.stem:
            return False
    return True


def _evidence_hashes(directory: Path) -> list[str] | None:
    """Return validated content hashes for a present redacted evidence archive."""
    evidence_dir = directory / "evidence"
    if not evidence_dir.exists():
        return []
    if evidence_dir.is_symlink() or not evidence_dir.is_dir():
        return None
    hashes = []
    for path in evidence_dir.iterdir():
        if path.is_symlink() or not path.is_file() or path.suffix != ".json":
            return None
        if _SHA256.fullmatch(path.stem) is None:
            return None
        try:
            content = path.read_bytes()
        except OSError:
            return None
        if hashlib.sha256(content).hexdigest() != path.stem:
            return None
        hashes.append(path.stem)
    return sorted(hashes)


def _evidence_matches_previous_report(directory: Path, hashes: list[str]) -> bool:
    """Ensure a valid prior report still names the present archive files."""
    report_path = directory / "verification.json"
    digest_path = directory / "verification.sha256"
    if not report_path.exists() and not digest_path.exists():
        return True
    if not report_path.exists() or not digest_path.exists():
        return False
    try:
        content = report_path.read_bytes()
        digest = digest_path.read_text(encoding="ascii").strip()
        report = json.loads(content)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if hashlib.sha256(content).hexdigest() != digest or not isinstance(report, dict):
        return False
    previous = report.get("evidence_sha256")
    if previous is None:
        return True
    return previous == hashes


def _write_verification(directory: Path, report: dict[str, Any]) -> None:
    """Publish a stable public verification snapshot and its integrity digest."""
    data = canonical_json(report)
    _write_atomic(directory / "verification.json", data)
    _write_atomic(
        directory / "verification.sha256", hashlib.sha256(data).hexdigest().encode("ascii")
    )


def _write_atomic(path: Path, data: bytes, *, exclusive: bool = False) -> None:
    """Write one report atomically, optionally refusing to replace an archive."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".report-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
