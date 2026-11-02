"""Trusted source identity and controlled sample/configuration adapters."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping, Protocol

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
        reference = sample.get("source_ref")
        paths = self.source_map.get(reference)
        if not isinstance(paths, Mapping) or set(paths) != {"input", "text"}:
            raise ValueError("experiment_sample_source_invalid")
        hashes = {}
        for kind in ("input", "text"):
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
            except (OSError, RuntimeError, UnicodeError, ValueError):
                raise ValueError("experiment_sample_source_invalid") from None
            hashes[f"{kind}_sha256"] = hashlib.sha256(content).hexdigest()
        return hashes


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


def _sensitive_sample_path(parts: Any) -> bool:
    normalized = [str(part).replace("\\", "/").casefold() for part in parts]
    return (
        normalized == ["tests", "test.md"]
        or any(
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
    )


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
