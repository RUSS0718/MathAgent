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


def verify_pair_arm_component_config(
    job_reader: Any, job_id: str, pair: Any, arm: str
) -> dict[str, Any]:
    """Read one public Job and compare its applied config with its frozen arm."""
    if not isinstance(job_id, str) or not _IDENTIFIER.fullmatch(job_id):
        return {"status": "FAIL", "reason": "experiment_pair_job_id_invalid"}
    try:
        registration = validate_pair_manifest(pair)
        if arm not in {"baseline", "variant"}:
            raise ValueError
    except (TypeError, ValueError):
        return {"status": "FAIL", "reason": "experiment_pair_manifest_invalid"}

    try:
        job = job_reader.request("GET", f"/api/agent/jobs/{job_id}")
    except Exception:
        return {"status": "UNKNOWN", "reason": "experiment_pair_job_unavailable"}
    if not isinstance(job, dict):
        return {"status": "UNKNOWN", "reason": "experiment_pair_job_unavailable"}

    result = job.get("result")
    binding = result.get("experiment_pair") if isinstance(result, dict) else None
    expected_arm = registration[arm]
    expected = expected_arm["features"]
    if (
        job.get("job_id") != job_id
        or job.get("status") != "succeeded"
        or not isinstance(result, dict)
        or result.get("solver_mode") != expected_arm["manifest"]["model"]["solver_mode"]
        or result.get("execution_mode") != expected_arm["manifest"]["model"]["solver_mode"]
        or not isinstance(binding, dict)
        or binding.get("pair_id") != registration["pair_id"]
        or binding.get("pair_sha256") != pair_manifest_digest(registration)
        or binding.get("arm") != arm
        or binding.get("arm_run_id") != expected_arm["run_id"]
        or binding.get("factor") != registration["factor"]
        or binding.get("features") != expected
        or binding.get("applied_config_status") != "applied"
        or binding.get("applied_component_config") != expected
    ):
        return {"status": "FAIL", "reason": "experiment_pair_arm_identity_or_config_mismatch"}

    solver = result.get("solver")
    if not isinstance(solver, dict) or solver.get("run_id") != job_id:
        return {"status": "FAIL", "reason": "experiment_pair_solver_run_identity_mismatch"}
    return {"status": "PASS", "applied_component_config": dict(expected)}


def _result(pair_id: str, status: str, reason: str) -> dict[str, Any]:
    """Return a minimal public verification projection."""
    return {"schema_version": 1, "pair_id": pair_id, "status": status, "reason": reason}
