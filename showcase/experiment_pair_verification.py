"""Read-only pair-state checks that never trust the runner's completion claim."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .experiment_pair import pair_manifest_digest, validate_pair_manifest

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")


def verify_experiment_pair(
    pair_id: str, *, output_root: str | Path = "artifacts/experiments"
) -> dict[str, Any]:
    """Validate the frozen pair and report NOT_RUN or UNKNOWN without deriving PASS."""
    if not isinstance(pair_id, str) or not _IDENTIFIER.fullmatch(pair_id):
        raise ValueError("experiment_pair_id_invalid")
    directory = Path(output_root) / "pairs" / pair_id
    try:
        registration = json.loads((directory / "registration.json").read_text(encoding="utf-8"))
        state = json.loads((directory / "status.json").read_text(encoding="utf-8"))
        validate_pair_manifest(registration)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        raise ValueError("experiment_pair_state_invalid") from None
    digest = pair_manifest_digest(registration)
    if (
        not isinstance(state, dict)
        or state.get("pair_id") != pair_id
        or state.get("pair_sha256") != digest
        or state.get("factor") != registration["factor"]
    ):
        return _result(pair_id, "UNKNOWN", "experiment_pair_registration_mismatch")
    arms = state.get("arms")
    readiness = state.get("readiness")
    not_dispatched = not any(
        (Path(output_root) / registration[name]["run_id"]).exists()
        for name in ("baseline", "variant")
    )
    if (
        isinstance(arms, dict)
        and isinstance(readiness, dict)
        and state.get("status") == "NOT_RUN"
        and state.get("phase") == "readiness_blocked"
        and state.get("execution_order") == []
        and state.get("dispatch_count") == 0
        and readiness.get("status") == "NOT_RUN"
        and not_dispatched
        and all(
            isinstance(arms.get(name), dict)
            and arms[name].get("status") == "not_started"
            and arms[name].get("verification_status") == "NOT_RUN"
            for name in ("baseline", "variant")
        )
    ):
        return _result(pair_id, "NOT_RUN", state.get("stop_reason", "pair_not_dispatched"))
    return _result(pair_id, "UNKNOWN", "paired_arm_reverification_unavailable")


def _result(pair_id: str, status: str, reason: str) -> dict[str, Any]:
    """Return a minimal public verification projection."""
    return {"schema_version": 1, "pair_id": pair_id, "status": status, "reason": reason}
