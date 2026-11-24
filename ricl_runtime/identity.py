"""Stable identifiers for Runtime evidence and results."""

import hashlib
import json
from typing import Any


def stable_id(prefix: str, value: Any) -> str:
    """Build a content-addressed identifier from canonical JSON data."""

    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"