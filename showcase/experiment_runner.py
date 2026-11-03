"""Immutable local Run registration and zero-dispatch preflight."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from .experiment_manifest import (
    canonical_json,
    is_executable_evidence_kind,
    manifest_digest,
    validate_manifest,
)
from .experiment_samples import FileSampleHashResolver
from .experiment_sources import (
    ModelConfigAdapter,
    is_sensitive_path,
    server_model_config_matches,
)

_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")


class TransportManifestAdapter(Protocol):
    """Narrow seam for #124's finalized transport/profile identity contract."""

    def validate_manifest_transport(self, transport: dict[str, Any]) -> None: ...


def load_manifest(path: str | Path) -> dict[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("experiment_manifest_invalid")
            value[key] = item
        return value

    try:
        candidate = Path(path)
        if is_sensitive_path(candidate):
            raise ValueError
        resolved = candidate.resolve(strict=True)
        if is_sensitive_path(resolved):
            raise ValueError
        with resolved.open("r", encoding="utf-8") as stream:
            manifest = json.load(stream, object_pairs_hook=unique_object)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        raise ValueError("experiment_manifest_unreadable") from None
    return validate_manifest(manifest)


def preflight_manifest(
    manifest: Any,
    *,
    expected_sha256: str,
    current_source: dict[str, Any],
    trusted_model_config: ModelConfigAdapter | None,
    sample_resolver: FileSampleHashResolver | None,
    transport_adapter: TransportManifestAdapter | None,
    server_model_config: ModelConfigAdapter | None = None,
) -> dict[str, Any]:
    """Check frozen inputs without creating clients, Jobs, tools, or requests."""
    checks = {
        "manifest": "failed",
        "manifest_sha256": "failed",
        "evidence_kind": "not_checked",
        "execution_authorization": "not_checked",
        "retry": "not_checked",
        "source_identity": "failed",
        "model": "not_checked",
        "transport": "not_checked",
        "samples": "not_checked",
        "budgets": "not_checked",
        "stop_rules": "not_checked",
    }
    try:
        record = validate_manifest(manifest)
    except ValueError:
        return _preflight_result(False, None, checks, ["experiment_manifest_invalid"])
    checks["manifest"] = "passed"
    checks.update(budgets="passed", stop_rules="passed")

    actual_sha256 = manifest_digest(record)
    if not _is_sha256(expected_sha256) or actual_sha256 != expected_sha256:
        return _preflight_result(
            False, actual_sha256, checks, ["experiment_manifest_hash_mismatch"]
        )
    checks["manifest_sha256"] = "passed"
    if record["source_identity"] != current_source:
        return _preflight_result(
            False, actual_sha256, checks, ["experiment_source_identity_mismatch"]
        )
    checks["source_identity"] = "passed"
    if not is_executable_evidence_kind(record["evidence_kind"]):
        checks["evidence_kind"] = "failed"
        return _preflight_result(
            False,
            actual_sha256,
            checks,
            ["experiment_evidence_kind_unavailable"],
        )
    checks["evidence_kind"] = "passed"
    if (
        record["evidence_kind"] == "provider_live"
        and record["authorization"]["execution_authorized"] is not True
    ):
        checks["execution_authorization"] = "failed"
        return _preflight_result(
            False,
            actual_sha256,
            checks,
            ["experiment_live_authorization_required"],
        )
    checks["execution_authorization"] = "passed"
    if record["model"]["retry"] != 0:
        checks["retry"] = "failed"
        return _preflight_result(False, actual_sha256, checks, ["experiment_retry_unsupported"])
    checks["retry"] = "passed"
    errors = []
    model_fingerprint = None
    if trusted_model_config is None:
        errors.append("experiment_model_config_unavailable")
    else:
        try:
            actual_model = dict(trusted_model_config.config())
            model_fingerprint = (
                __import__("hashlib").sha256(canonical_json(actual_model)).hexdigest()
            )
        except Exception:
            actual_model = None
        if actual_model == record["model"]:
            checks["model"] = "passed"
        else:
            checks["model"] = "failed"
            errors.append("experiment_model_config_mismatch")
    if server_model_config is None:
        checks["server_model"] = "failed"
        errors.append("experiment_server_model_config_unavailable")
    else:
        try:
            server_model = server_model_config.config()
            server_matches = server_model_config_matches(server_model, record)
        except Exception:
            server_matches = False
        if server_matches:
            checks["server_model"] = "passed"
        else:
            checks["server_model"] = "failed"
            errors.append("experiment_server_model_config_mismatch")
    if sample_resolver is None:
        errors.append("experiment_sample_resolver_unavailable")
    else:
        try:
            samples_match = all(
                sample_resolver.hashes(sample)
                == {
                    "input_sha256": sample["input_sha256"],
                    "text_sha256": sample["text_sha256"],
                }
                for sample in record["samples"]
            )
        except Exception:
            samples_match = False
        if samples_match:
            checks["samples"] = "passed"
        else:
            checks["samples"] = "failed"
            errors.append("experiment_sample_hash_mismatch")
    if transport_adapter is None:
        errors.append("experiment_transport_adapter_unavailable")
    else:
        try:
            transport_adapter.validate_manifest_transport(record["transport"])
        except Exception:
            errors.append("experiment_transport_profile_mismatch")
        else:
            checks["transport"] = "passed"
    return _preflight_result(
        not errors, actual_sha256, checks, errors, model_fingerprint=model_fingerprint
    )


def register_run(
    manifest: Any,
    *,
    expected_sha256: str,
    run_id: str,
    output_root: str | Path = "artifacts/experiments",
    current_source: dict[str, Any],
    trusted_model_config: ModelConfigAdapter | None,
    sample_resolver: FileSampleHashResolver | None,
    transport_adapter: TransportManifestAdapter | None,
    server_model_config: ModelConfigAdapter | None = None,
) -> dict[str, Any]:
    """Register one exact manifest once; the manifest snapshot is write-once."""
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise ValueError("experiment_run_id_invalid")
    result = preflight_manifest(
        manifest,
        expected_sha256=expected_sha256,
        current_source=current_source,
        trusted_model_config=trusted_model_config,
        server_model_config=server_model_config,
        sample_resolver=sample_resolver,
        transport_adapter=transport_adapter,
    )
    if not result["ready"]:
        raise ValueError(result["errors"][0])
    record = validate_manifest(manifest)
    directory = Path(output_root) / run_id
    try:
        directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise ValueError("experiment_run_exists") from None
    (directory / "manifest.json").write_bytes(canonical_json(record))
    (directory / "manifest.sha256").write_text(result["manifest_sha256"] + "\n", encoding="ascii")
    status = {
        "schema_version": 1,
        "run_id": run_id,
        "manifest_sha256": result["manifest_sha256"],
        "pid": os.getpid(),
        "process_created_at": _process_created_at(),
        "phase": "registered",
        "completed": 0,
        "total": len(record["samples"]),
        "stop_reason": None,
        "log_tail": [],
    }
    _write_status(directory / "status.json", status)
    return status


def read_status(
    run_id: str, *, output_root: str | Path = "artifacts/experiments"
) -> dict[str, Any]:
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise ValueError("experiment_run_id_invalid")
    directory = Path(output_root) / run_id
    try:
        status = json.loads((directory / "status.json").read_text(encoding="utf-8"))
        saved_hash = (directory / "manifest.sha256").read_text(encoding="ascii").strip()
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError("experiment_run_not_found") from None
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("experiment_run_state_invalid") from None
    if (
        not isinstance(status, dict)
        or status.get("run_id") != run_id
        or status.get("manifest_sha256") != saved_hash
        or manifest_digest(manifest) != saved_hash
    ):
        raise ValueError("experiment_run_state_invalid")
    return status


def _preflight_result(
    ready: bool,
    digest: str | None,
    checks: dict[str, str],
    errors: list[str],
    *,
    model_fingerprint: str | None = None,
) -> dict[str, Any]:
    return {
        "ready": ready,
        "manifest_sha256": digest,
        "model_config_sha256": model_fingerprint,
        "checks": checks,
        "errors": errors,
        "dispatch_count": 0,
    }


def _write_status(path: Path, status: dict[str, Any]) -> None:
    payload = json.dumps(status, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".status-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _process_created_at() -> str:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class FileTime(ctypes.Structure):
            _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

        created, exited, kernel, user = FileTime(), FileTime(), FileTime(), FileTime()
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_current_process = kernel32.GetCurrentProcess
        get_current_process.restype = wintypes.HANDLE
        get_process_times = kernel32.GetProcessTimes
        get_process_times.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(FileTime),
            ctypes.POINTER(FileTime),
            ctypes.POINTER(FileTime),
            ctypes.POINTER(FileTime),
        ]
        get_process_times.restype = wintypes.BOOL
        if not get_process_times(
            get_current_process(),
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            raise ValueError("experiment_process_identity_unavailable")
        windows_ticks = (created.high << 32) | created.low
        timestamp = windows_ticks / 10_000_000 - 11_644_473_600
    else:
        try:
            fields = Path("/proc/self/stat").read_text(encoding="ascii").rsplit(")", 1)[1].split()
            start_ticks = int(fields[19])
            boot_time = next(
                int(line.split()[1])
                for line in Path("/proc/stat").read_text(encoding="ascii").splitlines()
                if line.startswith("btime ")
            )
            timestamp = boot_time + start_ticks / os.sysconf("SC_CLK_TCK")
        except (OSError, StopIteration, ValueError, IndexError):
            raise ValueError("experiment_process_identity_unavailable") from None
    return (
        datetime.fromtimestamp(timestamp, UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
