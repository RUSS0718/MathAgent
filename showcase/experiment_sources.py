"""Trusted source identity and controlled sample/configuration adapters."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from .experiment_manifest import canonical_json

_APPLIED_MODEL_KEYS = {
    "name", "thinking_mode", "temperature", "max_output_tokens",
    "request_timeout_seconds", "retry", "solver_mode", "verification_mode",
}
_SERVER_MODEL_KEYS = {
    "name", "thinking_mode", "temperature", "max_output_tokens",
    "request_timeout_seconds", "retry",
}
_SERVER_CONFIG_KEYS = {
    "schema_version", "status", "model", "solver_modes", "verification_modes",
    "transport", "config_sha256",
}


class FileAppliedModelConfig:
    """Read a strict, credential-free snapshot of already applied model settings."""

    def __init__(self, path: str | Path) -> None:
        value = _read_control_json(path, "experiment_model_config_invalid")
        if not isinstance(value, dict) or set(value) != {"schema_version", "model"}:
            raise ValueError("experiment_model_config_invalid")
        model = value.get("model")
        if (
            value.get("schema_version") != 1
            or not isinstance(model, dict)
            or set(model) != _APPLIED_MODEL_KEYS
            or not isinstance(model.get("name"), str)
            or type(model.get("thinking_mode")) is not bool
            or type(model.get("temperature")) not in {int, float}
            or not math.isfinite(model["temperature"])
            or type(model.get("max_output_tokens")) is not int
            or type(model.get("request_timeout_seconds")) not in {int, float}
            or not math.isfinite(model["request_timeout_seconds"])
            or type(model.get("retry")) is not int
            or not isinstance(model.get("solver_mode"), str)
            or not isinstance(model.get("verification_mode"), str)
        ):
            raise ValueError("experiment_model_config_invalid")
        self._model = dict(model)

    def config(self) -> Mapping[str, Any]:
        return dict(self._model)

    def fingerprint(self) -> str:
        return hashlib.sha256(canonical_json(self._model)).hexdigest()


class ModelConfigAdapter(Protocol):
    """Pure seam exposing already trusted, applied model settings."""

    def config(self) -> Mapping[str, Any]: ...


class StaticModelConfigAdapter:
    """Test and loopback adapter; runtime construction stays outside preflight."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        self._config = dict(config)

    def config(self) -> Mapping[str, Any]:
        return dict(self._config)


class ServerAppliedModelConfigAdapter:
    """Read the public, versioned applied-config projection from a Showcase server."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def config(self) -> Any:
        response = self.client.request("GET", "/api/capabilities")
        if not isinstance(response, dict):
            raise ValueError("experiment_server_model_config_unavailable")
        return response.get("applied_model_config")


class StaticServerAppliedModelConfigAdapter:
    """Keep an untrusted server projection intact for strict boundary validation."""

    def __init__(self, value: Any) -> None:
        self.value = value

    def config(self) -> Any:
        return self.value


def server_model_config_matches(value: Any, manifest: Mapping[str, Any]) -> bool:
    """Validate the allowlisted server projection and compare active settings to a manifest."""
    if not isinstance(value, dict) or set(value) != _SERVER_CONFIG_KEYS:
        return False
    if (
        type(value.get("schema_version")) is not int
        or value.get("schema_version") != 1
        or value.get("status") != "available"
        or not isinstance(value.get("model"), dict)
        or set(value["model"]) != _SERVER_MODEL_KEYS
        or not isinstance(value.get("solver_modes"), list)
        or any(not isinstance(item, str) for item in value["solver_modes"])
        or len(set(value["solver_modes"])) != len(value["solver_modes"])
        or not isinstance(value.get("verification_modes"), list)
        or any(not isinstance(item, str) for item in value["verification_modes"])
        or len(set(value["verification_modes"])) != len(value["verification_modes"])
    ):
        return False
    model = value["model"]
    if (
        not isinstance(model["name"], str)
        or not model["name"].strip()
        or type(model["thinking_mode"]) is not bool
        or type(model["temperature"]) not in {int, float}
        or not math.isfinite(model["temperature"])
        or model["temperature"] < 0
        or type(model["max_output_tokens"]) is not int
        or model["max_output_tokens"] <= 0
        or type(model["request_timeout_seconds"]) is not int
        or model["request_timeout_seconds"] <= 0
        or type(model["retry"]) is not int
        or model["retry"] < 0
    ):
        return False
    transport = value.get("transport")
    if (
        not isinstance(transport, dict)
        or set(transport) != {"policy", "profile_set_fingerprint"}
        or transport.get("policy") not in {"legacy", "stream_first"}
        or not _is_hash(transport.get("profile_set_fingerprint"))
        or not _is_hash(value.get("config_sha256"))
    ):
        return False
    fingerprint_input = {key: item for key, item in value.items() if key != "config_sha256"}
    if hashlib.sha256(canonical_json(fingerprint_input)).hexdigest() != value["config_sha256"]:
        return False
    expected_model = manifest.get("model")
    expected_transport = manifest.get("transport")
    return (
        isinstance(expected_model, Mapping)
        and all(model[key] == expected_model[key] for key in _SERVER_MODEL_KEYS)
        and expected_model.get("solver_mode") in value["solver_modes"]
        and expected_model.get("verification_mode") in value["verification_modes"]
        and isinstance(expected_transport, Mapping)
        and transport["policy"] == expected_transport.get("policy")
        and transport["profile_set_fingerprint"]
        == expected_transport.get("profile_set_fingerprint")
    )


def source_identity(root: str | Path | None = None) -> dict[str, Any]:
    """Hash relevant Python/config sources and report source-only Git dirtiness."""
    repository = Path(root).resolve() if root is not None else Path(__file__).resolve().parents[1]
    revision = _git(repository, "rev-parse", "HEAD").decode("ascii").strip()
    listed = _git(repository, "ls-files", "-co", "--exclude-standard", "-z").decode(
        "utf-8", errors="surrogateescape"
    ).split("\0")
    names = sorted({name for name in listed if name and _is_source_path(name)})
    file_hashes = {}
    for name in names:
        path = repository.joinpath(*name.split("/"))
        file_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

    status = _git(repository, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    entries = status.decode("utf-8", errors="surrogateescape").split("\0")
    dirty_paths = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        path = entry[3:]
        if path and _is_source_path(path):
            dirty_paths.append(path)
        if entry[:2].find("R") >= 0 or entry[:2].find("C") >= 0:
            index += 1
    dirty_paths = sorted(set(dirty_paths))
    return {
        "revision": revision,
        "source_sha256": hashlib.sha256(
            json.dumps(
                file_hashes,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest(),
        "dirty_status": "dirty" if dirty_paths else "clean",
        "dirty_paths": dirty_paths,
    }


def is_sensitive_path(path: Any) -> bool:
    """Reject reserved and generated paths before any caller-controlled file read."""
    raw_parts = (
        list(path)
        if isinstance(path, (list, tuple))
        else str(path).replace("\\", "/").split("/")
    )
    normalized = []
    for value in raw_parts:
        part = str(value).replace("\\", "/").casefold()
        for component in part.split("/"):
            if component in {"", "."}:
                continue
            if component == "..":
                if normalized and normalized[-1] != "..":
                    normalized.pop()
                else:
                    normalized.append(component)
                continue
            normalized.append(component)
    return (
        len(normalized) >= 2
        and normalized[-2:] == ["tests", "test.md"]
    ) or any(
        part.startswith(".env")
        or part in {
            ".git",
            ".venv",
            "venv",
            "artifacts",
            "raw",
            "node_modules",
            "__pycache__",
            ".local",
            ".scratch",
        }
        for part in normalized
    )


def _read_control_json(path: str | Path, error_code: str) -> Any:
    try:
        resolved = Path(path).resolve(strict=True)
        if is_sensitive_path(resolved.parts) or not resolved.is_file():
            raise ValueError

        def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError
                result[key] = value
            return result

        with resolved.open("r", encoding="utf-8") as stream:
            return json.load(stream, object_pairs_hook=unique_object)
    except (OSError, RuntimeError, UnicodeError, ValueError, json.JSONDecodeError):
        raise ValueError(error_code) from None


def _git(root: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ["git", *arguments], cwd=root, capture_output=True, check=True
    ).stdout


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _is_source_path(name: str) -> bool:
    normalized = name.replace("\\", "/")
    parts = normalized.split("/")
    # Filter the caller-reserved file before resolving or reading any source path.
    if normalized == "tests/test.md":
        return False
    if any(part in {".venv", "venv", "artifacts", "raw", "__pycache__", "node_modules"} for part in parts):
        return False
    if parts[0].startswith(".env") or parts[0] in {".git", ".local", ".scratch"}:
        return False
    if parts[0] in {"showcase", "scripts", "tests"}:
        return normalized.endswith(".py")
    if len(parts) == 1 and normalized.endswith(".py"):
        return normalized != "user_agent.py"
    return normalized in {"pyproject.toml", "uv.lock", ".python-version"}
