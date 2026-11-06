"""Read-only pair-state checks that never trust the runner's completion claim."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .experiment_pair import pair_manifest_digest, validate_pair_manifest

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")


def verify_experiment_pair(
    pair_id: str,
    *,
    output_root: str | Path = "artifacts/experiments",
    read_client: Any = None,
) -> dict[str, Any]:
    """Reconcile each frozen arm against saved Run and public Job evidence."""
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
    if read_client is None:
        return _result(pair_id, "UNKNOWN", "paired_arm_reverification_unavailable")
    if (
        state.get("status") != "PASS"
        or state.get("phase") != "completed"
        or state.get("execution_order") != ["baseline", "variant"]
        or state.get("dispatch_count") != 2
        or state.get("completed") != 2
        or not isinstance(arms, dict)
        or not isinstance(readiness, dict)
        or readiness.get("status") != "PASS"
        or readiness.get("issue_number") != 127
        or readiness.get("report_sha256") != registration["readiness_report_sha256"]
    ):
        return _result(pair_id, "UNKNOWN", "paired_execution_incomplete")

    from .experiment_execution_state import load_registered_manifest
    from .experiment_manifest import manifest_digest
    from .experiment_runner import read_status
    from .experiment_verification import verify_experiment_run

    verified_arms = {}
    for name in ("baseline", "variant"):
        registered = registration[name]
        arm_state = arms.get(name)
        if not isinstance(arm_state, dict):
            return _result(pair_id, "UNKNOWN", "paired_arm_state_unavailable")
        try:
            run_status = read_status(registered["run_id"], output_root=output_root)
            run_manifest = load_registered_manifest(Path(output_root) / registered["run_id"])
            run_report = verify_experiment_run(
                registered["run_id"], output_root=output_root, read_client=read_client
            )
        except (OSError, ValueError, TypeError):
            return _result(pair_id, "UNKNOWN", "paired_arm_verification_unavailable")
        if manifest_digest(run_manifest) != manifest_digest(registered["manifest"]):
            return _result(pair_id, "FAIL", "paired_arm_manifest_mismatch")
        if run_status.get("phase") != "completed" or run_report.get("status") != "PASS":
            status_value = "FAIL" if run_report.get("status") == "FAIL" else "UNKNOWN"
            return _result(pair_id, status_value, "paired_arm_run_not_verified")
        records = run_status.get("run_records")
        samples = registered["manifest"]["samples"]
        if not isinstance(records, list) or len(records) != len(samples):
            return _result(pair_id, "FAIL", "paired_arm_sample_identity_mismatch")
        by_sample = {item.get("sample_id"): item for item in records if isinstance(item, dict)}
        outcomes = []
        observed_configs = []
        for sample in samples:
            record = by_sample.get(sample["id"])
            job_id = record.get("job_id") if isinstance(record, dict) else None
            if not isinstance(job_id, str):
                return _result(pair_id, "FAIL", "paired_arm_sample_identity_mismatch")
            component = verify_pair_arm_component_config(read_client, job_id, registration, name)
            if component.get("status") != "PASS":
                return _result(
                    pair_id,
                    component.get("status", "UNKNOWN"),
                    component.get("reason", "paired_arm_component_verification_failed"),
                )
            observed_configs.append(component["applied_component_config"])
            evidence = _read_sample_evidence(Path(output_root) / registered["run_id"], sample["id"])
            if evidence is None or evidence.get("job_id") != job_id:
                return _result(pair_id, "UNKNOWN", "paired_arm_sample_evidence_unavailable")
            outcomes.append(_sample_outcome(evidence, run_report.get("status")))
        if len({json.dumps(value, sort_keys=True) for value in observed_configs}) != 1:
            return _result(pair_id, "FAIL", "experiment_pair_applied_config_mismatch")
        if (
            arm_state.get("run_id") != registered["run_id"]
            or arm_state.get("manifest_sha256") != manifest_digest(registered["manifest"])
            or arm_state.get("status") != "completed"
            or arm_state.get("execution_phase") != "completed"
            or arm_state.get("stop_reason") is not None
            or arm_state.get("job_ids") != [item["job_id"] for item in outcomes]
            or arm_state.get("sample_outcomes") != outcomes
            or arm_state.get("applied_component_config") != observed_configs[0]
            or arm_state.get("verification_status") != "PASS"
        ):
            return _result(pair_id, "FAIL", "paired_arm_record_mismatch")
        verified_arms[name] = {
            "run_id": registered["run_id"],
            "manifest_sha256": manifest_digest(registered["manifest"]),
            "verification_status": run_report["status"],
            "applied_component_config": observed_configs[0],
            "sample_outcomes": outcomes,
        }
    return {
        "schema_version": 1,
        "pair_id": pair_id,
        "status": "PASS",
        "reason": "paired_arms_independently_verified",
        "factor": registration["factor"],
        "config_difference": {
            "factor": registration["factor"],
            "baseline": verified_arms["baseline"]["applied_component_config"][
                registration["factor"]
            ],
            "variant": verified_arms["variant"]["applied_component_config"][
                registration["factor"]
            ],
        },
        "execution_order": ["baseline", "variant"],
        "arms": verified_arms,
    }


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


def _read_sample_evidence(directory: Path, sample_id: str) -> dict[str, Any] | None:
    """Read exactly one redacted evidence record for a registered sample."""
    matches = []
    try:
        for path in (directory / "evidence").glob("*.json"):
            item = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(item, dict) and item.get("sample_id") == sample_id:
                matches.append(item)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return matches[0] if len(matches) == 1 else None


def _sample_outcome(
    evidence: dict[str, Any], verification_status: str, *, stop_reason: str | None = None
) -> dict[str, Any]:
    """Project per-sample job, usage, tool, transport and delivery observations."""
    budget = evidence.get("budget")
    semantics = evidence.get("semantics")
    review = evidence.get("whole_review")
    return {
        "sample_id": evidence.get("sample_id"),
        "job_id": evidence.get("job_id"),
        "verification_status": verification_status,
        "status": verification_status,
        "job_status": evidence.get("job_status"),
        "transport_identity": evidence.get("transport_identity"),
        "usage": budget,
        "tool_calls": budget.get("tool_calls") if isinstance(budget, dict) else None,
        "tools": evidence.get("tools", []),
        "stop_reason": stop_reason,
        "whole_review": review,
        "semantics": semantics,
        "request_attempts": evidence.get("request_attempts"),
    }
