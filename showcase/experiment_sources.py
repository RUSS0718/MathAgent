"""Trusted source identity and controlled sample/configuration adapters."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from collections.abc import Mapping
from pathlib import Path, PureWindowsPath
from typing import Any, Protocol

from .experiment_manifest import canonical_json

_APPLIED_MODEL_KEYS = {
    "name", "thinking_mode", "temperature", "max_output_tokens",
    "request_timeout_seconds", "retry", "solver_mode", "verification_mode",
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


def load_sample_map(path: str | Path) -> dict[str, dict[str, str]]:
    """Load only opaque sample IDs mapped to two relative file references."""
    value = _read_control_json(path, "experiment_sample_map_invalid")
    if not isinstance(value, dict) or any(
        not isinstance(sample_id, str)
        or not isinstance(paths, dict)
        or set(paths) != {"input", "text"}
        or any(not isinstance(relative, str) or not relative for relative in paths.values())
        for sample_id, paths in value.items()
    ):
        raise ValueError("experiment_sample_map_invalid")
    return value

class ModelConfigAdapter(Protocol):
    """Pure seam exposing already trusted, applied model settings."""

    def config(self) -> Mapping[str, Any]: ...


class StaticModelConfigAdapter:
    """Test and loopback adapter; runtime construction stays outside preflight."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        self._config = dict(config)

    def config(self) -> Mapping[str, Any]:
        return dict(self._config)


class FileSampleHashResolver:
    """Resolve opaque sample refs through a fixed map and hash files inside one root."""

    def __init__(self, data_root: str | Path, source_map: Mapping[str, Mapping[str, str]]) -> None:
        try:
            root = Path(data_root).resolve(strict=True)
        except (OSError, RuntimeError):
            raise ValueError("experiment_sample_source_invalid") from None
        if (
            not root.is_dir()
            or _sensitive_sample_path(root.parts)
            or not isinstance(source_map, Mapping)
        ):
            raise ValueError("experiment_sample_source_invalid")
        self.root = root
        self.source_map = dict(source_map)

    def hashes(self, sample: dict[str, Any]) -> dict[str, str]:
        return {
            f"{kind}_sha256": hashlib.sha256(self._read(sample, kind)).hexdigest()
            for kind in ("input", "text")
        }

    def read_text(self, sample: dict[str, Any]) -> str:
        """Read the mapped text only after both frozen sample hashes still match."""
        input_bytes = self._read(sample, "input")
        text_bytes = self._read(sample, "text")
        if (
            hashlib.sha256(input_bytes).hexdigest() != sample.get("input_sha256")
            or hashlib.sha256(text_bytes).hexdigest() != sample.get("text_sha256")
        ):
            raise ValueError("experiment_sample_hash_mismatch")
        try:
            return text_bytes.decode("utf-8", errors="strict")
        except UnicodeError:
            raise ValueError("experiment_sample_source_invalid") from None

    def _read(self, sample: dict[str, Any], kind: str) -> bytes:
        reference = sample.get("source_ref")
        paths = self.source_map.get(reference)
        if not isinstance(paths, Mapping) or set(paths) != {"input", "text"}:
            raise ValueError("experiment_sample_source_invalid")
        relative = paths[kind]
        if not isinstance(relative, str) or not relative:
            raise ValueError("experiment_sample_source_invalid")
        parts = relative.replace("\\", "/").split("/")
        if _unsafe_relative_sample_ref(relative, parts):
            raise ValueError("experiment_sample_source_invalid")
        try:
            candidate = self.root.joinpath(*parts)
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(self.root)
            if _sensitive_sample_path(resolved.relative_to(self.root).parts) or not resolved.is_file():
                raise ValueError
            content = resolved.read_bytes()
            content.decode("utf-8", errors="strict")
            return content
        except (OSError, RuntimeError, UnicodeError, ValueError):
            raise ValueError("experiment_sample_source_invalid") from None


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


def _unsafe_relative_sample_ref(relative: str, parts: list[str]) -> bool:
    return (
        Path(relative).is_absolute()
        or PureWindowsPath(relative).is_absolute()
        or bool(PureWindowsPath(relative).drive)
        or ":" in relative
        or ".." in parts
        or "\\" in relative
        or _sensitive_sample_path(parts)
    )


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


def _sensitive_sample_path(parts: Any) -> bool:
    return is_sensitive_path(parts)


def _read_control_json(path: str | Path, error_code: str) -> Any:
    try:
        resolved = Path(path).resolve(strict=True)
        if _sensitive_sample_path(resolved.parts) or not resolved.is_file():
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
