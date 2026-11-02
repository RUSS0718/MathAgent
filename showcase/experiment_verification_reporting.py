"""Create and persist allowlisted experiment verification reports."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .experiment_manifest import canonical_json
from .experiment_verification_state import _finite_number, _overall_status

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")
_PUBLIC_CALL_ID = re.compile(r"solver_call_[0-9a-f]{32}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _safe_evidence(
    sample: dict[str, Any],
    record: dict[str, Any],
    job: dict[str, Any],
    report: dict[str, Any],
    evidence: dict[str, Any],
    attempts: Any,
    budget: Any,
) -> dict[str, Any]:
    """Project public API responses into a report with no answer or prompt text."""
    projected_attempts = []
    for item in attempts if isinstance(attempts, list) else []:
        if not isinstance(item, dict):
            continue
        projection = {
            key: item.get(key)
            for key in (
                "attempt_id",
                "logical_call_id",
                "solver_call_id",
                "run_id",
                "role",
                "attempt_index",
                "status",
                "finish_reason",
                "requested_model",
                "usage",
                "usage_source",
                "metering_status",
                "thinking_mode",
                "temperature",
                "max_tokens",
                "requests_timeout_seconds",
                "effective_timeout_seconds",
                "retry_limit",
            )
        }
        if not isinstance(projection["solver_call_id"], str) or _PUBLIC_CALL_ID.fullmatch(
            projection["solver_call_id"]
        ) is None:
            projection.pop("solver_call_id")
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
    return {
        "sample_id": sample["id"],
        "job_id": record.get("job_id"),
        "job_status": job.get("status"),
        "execution_mode": report.get("mode"),
        "request_attempts": projected_attempts,
        "budget": _safe_budget(budget),
        "solver_mode": (job.get("result") or {}).get("solver_mode"),
        "semantics": {
            key: semantic.get(key)
            for key in (
                "execution",
                "transport",
                "whole_review",
                "binding",
                "formal_verification",
                "verification_requirement",
            )
        },
        "whole_review": {
            "scope": latest.get("scope"),
            "checker_version": latest.get("checker_version"),
            "accepted": "llm_whole_review_accepted" in latest.get("findings", []),
            "binding": verification.get("binding"),
            "artifact_sha256": (latest.get("artifact") or {}).get("sha256"),
            "source": {
                key: source.get(key)
                for key in (
                    "run_id",
                    "plan_version",
                    "attempt_index",
                    "state_revision",
                    "origin",
                    "candidate_version",
                )
            },
        },
        "transport_identity": _safe_transport(
            (evidence.get("solver") or {}).get("transport_identity")
        ),
    }


def _safe_budget(value: Any) -> dict[str, Any] | None:
    """Retain only numeric and categorical ledger fields for the archive."""
    if not isinstance(value, dict):
        return None
    keys = (
        "limits",
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
        if not _finite_number(number):
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
    if (
        not isinstance(value, dict)
        or value.get("policy") not in {"legacy", "stream_first"}
        or not isinstance(value.get("profile_set_fingerprint"), str)
        or _SHA256.fullmatch(value["profile_set_fingerprint"]) is None
        or not isinstance(value.get("calls"), list)
    ):
        return None
    calls = []
    for call in value["calls"]:
        if (
            not isinstance(call, dict)
            or not isinstance(call.get("call_id"), str)
            or _PUBLIC_CALL_ID.fullmatch(call["call_id"]) is None
            or not isinstance(call.get("role"), str)
            or _IDENTIFIER.fullmatch(call["role"]) is None
            or call.get("policy") != value["policy"]
            or call.get("transport") not in {"stream", "nonstream", "legacy"}
            or call.get("evidence_kind")
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
    if (
        not isinstance(report, dict)
        or report.get("run_id") != run_id
        or hashlib.sha256(content).hexdigest() != expected
        or report.get("status") != _overall_status(report.get("checks", {}))
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
