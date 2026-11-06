"""Durable JSON state helpers for experiment execution and recovery."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .experiment_manifest import validate_manifest
from .experiment_runner import _process_created_at, _write_status


def save_execution_status(directory: Path, status: dict[str, Any]) -> None:
    status["pid"] = os.getpid()
    status["process_created_at"] = _process_created_at()
    status["total"] = status.get("total", 0)
    _write_status(directory / "status.json", status)


def load_registered_manifest(directory: Path) -> dict[str, Any]:
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("experiment_run_state_invalid") from None
    return validate_manifest(manifest)


def read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("experiment_run_state_invalid") from None
    if not isinstance(value, dict):
        raise ValueError("experiment_run_state_invalid")
    return value


def write_json_once(path: Path, value: dict[str, Any]) -> None:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def remove_intent(path: Path) -> None:
    path.unlink(missing_ok=True)


def is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
