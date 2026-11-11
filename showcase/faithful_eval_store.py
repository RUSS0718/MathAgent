"""Sealed, create-once JSON evidence for explicit Faithful evaluations."""

import hashlib
import json
from pathlib import Path

from .experiment_manifest import canonical_json


def load_json(path):
    """Read public JSON with duplicate-key and sensitive-path rejection."""
    candidate = Path(path)
    if _sensitive(candidate) or _sensitive(candidate.resolve()):
        raise ValueError("faithful_sensitive_path")
    return json.loads(
        candidate.read_text(encoding="utf-8"),
        object_pairs_hook=_unique,
        parse_constant=_nonfinite,
    )


def write_sealed(path, value):
    """Create evidence and its byte hash once; never replace an existing result."""
    target = Path(path)
    payload = canonical_json(value)
    receipt = target.with_name(target.name + ".sha256")
    if target.exists() or receipt.exists():
        raise ValueError("faithful_evidence_exists")
    if _sensitive(target) or _sensitive(target.resolve()):
        raise ValueError("faithful_sensitive_path")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(payload)
    digest = hashlib.sha256(payload).hexdigest()
    with receipt.open("x", encoding="ascii") as stream:
        stream.write(digest)
    return digest


def read_sealed(path):
    """Verify a JSON member before parsing, refusing symlinks and broken receipts."""
    target = Path(path)
    receipt = target.with_name(target.name + ".sha256")
    if any(part.is_symlink() for part in (target, receipt, *target.parents)):
        raise ValueError("faithful_symlink")
    try:
        if hashlib.sha256(target.read_bytes()).hexdigest() != receipt.read_text(encoding="ascii"):
            raise ValueError("faithful_hash_mismatch")
        return load_json(target)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("faithful_evidence_invalid") from None


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("faithful_duplicate_json_key")
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError("faithful_nonfinite_json")


def _sensitive(path):
    """Allow the required artifacts directory while excluding secret/reserved inputs."""
    parts = [part.casefold() for part in Path(path).parts]
    return parts[-2:] == ["tests", "test.md"] or any(
        part.startswith(".env") or part in {".git", ".venv", "venv", "raw", "node_modules", "__pycache__"}
        for part in parts
    )
