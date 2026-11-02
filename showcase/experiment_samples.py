"""Resolve opaque sample identities through a fixed, guarded file map."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path, PureWindowsPath
from typing import Any

from .experiment_sources import _read_control_json, is_sensitive_path


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


class FileSampleHashResolver:
    """Resolve opaque sample refs through a fixed map and hash files inside one root."""

    def __init__(self, data_root: str | Path, source_map: Mapping[str, Mapping[str, str]]) -> None:
        try:
            root = Path(data_root).resolve(strict=True)
        except (OSError, RuntimeError):
            raise ValueError("experiment_sample_source_invalid") from None
        if (
            not root.is_dir()
            or is_sensitive_path(root.parts)
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
        if hashlib.sha256(input_bytes).hexdigest() != sample.get("input_sha256") or hashlib.sha256(
            text_bytes
        ).hexdigest() != sample.get("text_sha256"):
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
            if is_sensitive_path(resolved.relative_to(self.root).parts) or not resolved.is_file():
                raise ValueError
            content = resolved.read_bytes()
            content.decode("utf-8", errors="strict")
            return content
        except (OSError, RuntimeError, UnicodeError, ValueError):
            raise ValueError("experiment_sample_source_invalid") from None


def _unsafe_relative_sample_ref(relative: str, parts: list[str]) -> bool:
    return (
        Path(relative).is_absolute()
        or PureWindowsPath(relative).is_absolute()
        or bool(PureWindowsPath(relative).drive)
        or ":" in relative
        or ".." in parts
        or "\\" in relative
        or is_sensitive_path(parts)
    )
