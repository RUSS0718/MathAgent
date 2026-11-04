"""Persisted-state reads and aggregate status decisions for experiment verification."""

from __future__ import annotations

import math
import re
from typing import Any

_LEGACY_CHECKS = ("transport", "task", "usage", "coverage")
_CHECKS = (*_LEGACY_CHECKS, "process_path")
_CHECK_STATUSES = {"PASS", "FAIL", "UNKNOWN", "NOT_RUN"}
_STOP_REASONS = {
    "source_or_config_change",
    "hard_limit",
    "ledger_or_binding_defect",
    "unknown_transport",
    "transport_policy_rejected",
    "incomplete_or_unresolved_usage",
    "job_failed_or_canceled",
    "unknown_job_status",
    "unknown_session",
    "session_creation_unknown",
    "request_digest_unavailable",
    "request_digest_invalid",
    "unknown_dispatch",
    "resume_review_required",
    "resume_action_ambiguous",
    "unknown_resume",
}
_JOB_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")
_IDEMPOTENCY_KEY = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _finite_number(value: Any) -> bool:
    """Return whether an integer or float can be safely represented in reports."""
    if type(value) not in {int, float}:
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _index_records(value: Any) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Build a unique sample index and flag malformed persisted identities."""
    if not isinstance(value, list):
        return {}, ["run_records_invalid"]
    records: dict[str, dict[str, Any]] = {}
    errors = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("sample_id"), str):
            errors.append("run_record_invalid")
            continue
        sample_id = item["sample_id"]
        if sample_id in records:
            errors.append("duplicate_sample_record")
        records[sample_id] = item
    return records, errors


def _valid_run_record(
    record: dict[str, Any], sample: dict[str, Any], index: int, completed: list[int]
) -> bool:
    """Check stable identity fields before any remote report is trusted."""
    return (
        record.get("sample_id") == sample["id"]
        and isinstance(record.get("job_id"), str)
        and _JOB_ID.fullmatch(record["job_id"]) is not None
        and isinstance(record.get("session_id"), str)
        and bool(record["session_id"])
        and isinstance(record.get("idempotency_key"), str)
        and _IDEMPOTENCY_KEY.fullmatch(record["idempotency_key"]) is not None
        and isinstance(record.get("request_digest"), str)
        and _SHA256.fullmatch(record["request_digest"]) is not None
        and type(record.get("deadline_at")) in {int, float}
        and _finite_number(record["deadline_at"])
        and record["deadline_at"] > 0
        and (index not in completed or bool(record.get("job_id")))
    )


def _read_job_evidence(client: Any, record: dict[str, Any]) -> dict[str, Any]:
    """Read the idempotency projection, Job, report, and Evidence using GET only."""
    try:
        lookup = client.request(
            "GET",
            "/api/agent/jobs/by-idempotency",
            headers={
                "Idempotency-Key": record["idempotency_key"],
                "X-Request-Digest": record["request_digest"],
            },
        )
        if not isinstance(lookup, dict):
            return {"status": "UNKNOWN", "reason": "job_lookup_invalid"}
        if (
            lookup.get("job_id") != record["job_id"]
            or lookup.get("request_digest") != record["request_digest"]
        ):
            return {"status": "FAIL", "reason": "job_identity_mismatch"}
        job_id = record["job_id"]
        job = client.request("GET", f"/api/agent/jobs/{job_id}")
        report = client.request("GET", f"/api/agent/jobs/{job_id}/report")
        evidence = client.request("GET", f"/api/runs/{job_id}/evidence")
    except Exception:
        return {"status": "UNKNOWN", "reason": "job_evidence_unavailable"}
    if not all(isinstance(value, dict) for value in (job, report, evidence)):
        return {"status": "UNKNOWN", "reason": "job_evidence_invalid"}
    return {"status": "PASS", "lookup": lookup, "job": job, "report": report, "evidence": evidence}


def _coverage_check(
    status: dict[str, Any],
    manifest: dict[str, Any],
    records: dict[str, dict[str, Any]],
    completed: list[int],
    pending_intent: bool,
    failures: list[str],
    outcomes: list[dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    """Report whether every frozen sample has a reconciled terminal Job."""
    if failures:
        return _check("FAIL", "persisted_state_inconsistent")
    if pending_intent:
        return _check("UNKNOWN", "dispatch_intent_unresolved")
    coverage_statuses = [
        outcome.get("coverage", {}).get("status")
        for outcome in outcomes
        if isinstance(outcome.get("coverage"), dict)
    ]
    if "FAIL" in coverage_statuses:
        return _check("FAIL", "sample_evidence_inconsistent")
    if "UNKNOWN" in coverage_statuses:
        return _check("UNKNOWN", "sample_evidence_unavailable")
    if "NOT_RUN" in coverage_statuses:
        return _check("NOT_RUN", "required_samples_not_audited")
    if not records:
        return _check("NOT_RUN", "no_samples_dispatched")
    if status.get("phase") == "completed" and len(completed) == len(manifest["samples"]):
        return _check("PASS", "all_samples_completed")
    if status.get("phase") == "stopped" and status.get("stop_reason") in {
        "failure",
        "job_failed_or_canceled",
        "hard_limit",
    }:
        return _check("FAIL", "batch_stopped_before_completion")
    return _check("NOT_RUN", "required_samples_not_completed")


def _process_path_check(
    manifest: dict[str, Any], outcomes: list[dict[str, dict[str, Any]]]
) -> dict[str, Any]:
    """Require at least one audited natural planned trace when multistep is registered."""
    indices = [
        index
        for index, sample in enumerate(manifest["samples"])
        if sample.get("type") == "multistep"
    ]
    if not indices:
        return _check("PASS", "natural_multistep_not_required")
    checks = [
        outcomes[index].get("process_path", {})
        for index in indices
        if index < len(outcomes) and isinstance(outcomes[index], dict)
    ]
    observed = [item.get("status") for item in checks]
    if "FAIL" in observed:
        return _check("FAIL", "natural_multistep_evidence_inconsistent")
    if "PASS" in observed:
        return _check("PASS", "natural_multistep_path_observed")
    if "UNKNOWN" in observed:
        return _check("UNKNOWN", "natural_multistep_evidence_unavailable")
    if any(
        item.get("reason") in {
            "natural_multistep_trace_incomplete",
            "natural_multistep_delivery_unverified",
        }
        for item in checks
    ):
        return _check("NOT_RUN", "natural_multistep_path_incomplete")
    if any(item.get("reason") == "provider_live_trace_required" for item in checks):
        return _check("NOT_RUN", "provider_live_trace_required")
    return _check("NOT_RUN", "natural_multistep_path_not_observed")


def _process_coverage_summary(
    manifest: dict[str, Any],
    outcomes: list[dict[str, dict[str, Any]]],
    evidence: list[dict[str, Any]],
) -> dict[str, int]:
    """Report raw registered, audited, and path-observed counts without a rate claim."""
    indices = [
        index
        for index, sample in enumerate(manifest["samples"])
        if sample.get("type") == "multistep"
    ]
    evidence_by_id = {
        item.get("sample_id"): item
        for item in evidence
        if isinstance(item, dict) and isinstance(item.get("sample_id"), str)
    }
    statuses = []
    audited = 0
    completed_without_plan = 0
    planned = 0
    incomplete = 0
    not_provider_live = 0
    not_observed = 0
    not_run = 0
    for index in indices:
        outcome = outcomes[index] if index < len(outcomes) else {}
        if outcome.get("coverage", {}).get("status") == "PASS":
            audited += 1
        process_status = outcome.get("process_path", {}).get("status", "NOT_RUN")
        process_reason = outcome.get("process_path", {}).get("reason")
        statuses.append(process_status)
        summary = evidence_by_id.get(manifest["samples"][index]["id"], {}).get(
            "process_path", {}
        )
        plan_version = summary.get("plan_version") if isinstance(summary, dict) else None
        if type(plan_version) is int and plan_version > 0:
            planned += 1
        if process_status != "NOT_RUN":
            continue
        if outcome.get("coverage", {}).get("status") != "PASS":
            not_run += 1
            continue
        if process_reason == "natural_multistep_path_not_observed":
            if outcome.get("task", {}).get("status") == "PASS":
                completed_without_plan += 1
            not_observed += 1
        elif type(plan_version) is int and plan_version == 0:
            if outcome.get("task", {}).get("status") == "PASS":
                completed_without_plan += 1
            not_observed += 1
        elif type(plan_version) is int and plan_version > 0:
            if process_reason == "provider_live_trace_required":
                not_provider_live += 1
            elif process_reason in {
                "natural_multistep_trace_incomplete",
                "natural_multistep_delivery_unverified",
            }:
                incomplete += 1
            else:
                not_run += 1
        else:
            not_run += 1
    return {
        "registered": len(indices),
        "audited": audited,
        "completed_without_plan": completed_without_plan,
        "planned": planned,
        "path_completed": statuses.count("PASS"),
        "not_observed": not_observed,
        "incomplete": incomplete,
        "not_provider_live": not_provider_live,
        "unknown": statuses.count("UNKNOWN"),
        "not_run": not_run,
        "failed": statuses.count("FAIL"),
    }


def _aggregate_usage_mismatch(
    status: dict[str, Any],
    samples: list[dict[str, Any]],
    records: dict[str, dict[str, Any]],
    completed: list[int],
    budgets: dict[str, dict[str, Any]],
) -> str | None:
    """Compare runner totals with the independent ledgers of completed samples."""
    if not completed:
        return None
    totals = {
        "logical_calls": 0,
        "http_attempts": 0,
        "tool_calls": 0,
        "charged_tokens": 0,
        "wall_seconds": 0.0,
    }
    by_id = {sample["id"]: index for index, sample in enumerate(samples)}
    for sample_id, index in by_id.items():
        if index not in completed:
            continue
        budget = budgets.get(sample_id)
        if not isinstance(budget, dict):
            return None
        counters = ("logical_calls", "http_attempts", "tool_calls", "charged_tokens")
        if any(type(budget.get(key)) is not int or budget[key] < 0 for key in counters):
            return "batch_budget_counter_invalid"
        wall_seconds = budget.get("wall_time_seconds")
        if (
            type(wall_seconds) not in {int, float}
            or not _finite_number(wall_seconds)
            or wall_seconds < 0
        ):
            return "batch_budget_counter_invalid"
        totals["logical_calls"] += budget.get("logical_calls", 0)
        totals["http_attempts"] += budget.get("http_attempts", 0)
        totals["tool_calls"] += budget.get("tool_calls", 0)
        totals["charged_tokens"] += budget.get("charged_tokens", 0)
        totals["wall_seconds"] += budget.get("wall_time_seconds", 0)
        if sample_id not in records:
            return "completed_job_record_missing"
    stored = status.get("usage")
    if not isinstance(stored, dict) or any(
        stored.get(key) != value for key, value in totals.items()
    ):
        return "batch_usage_mismatch"
    return None


def _combine(values: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine sample-level outcomes without upgrading unknown evidence."""
    if not values:
        return _check("NOT_RUN", "no_samples")
    for candidate in ("FAIL", "UNKNOWN", "NOT_RUN"):
        for value in values:
            if value.get("status") == candidate:
                return _check(candidate, value.get("reason", "sample_check_incomplete"))
    return _check("PASS", "all_samples_passed")


def _check(status: str, reason: str) -> dict[str, Any]:
    """Create a public check result from a fixed status and reason code."""
    return {"status": status, "reason": reason}


def _overall_status(
    checks: Any,
    *,
    usage_policy: str = "required",
    check_names: tuple[str, ...] | None = None,
) -> str:
    """Derive the report result, optionally excluding observed-only usage unknowns."""
    if not isinstance(checks, dict):
        return "UNKNOWN"
    if check_names is not None:
        valid_shape = set(checks) == set(check_names)
    else:
        valid_shape = set(checks) in (set(_LEGACY_CHECKS), set(_CHECKS))
    if not valid_shape:
        return "UNKNOWN"
    statuses = [
        item.get("status") if isinstance(item, dict) else None
        for name, item in checks.items()
        if not (
            name == "usage"
            and usage_policy == "observe_only"
            and isinstance(item, dict)
            and item.get("status") == "UNKNOWN"
        )
    ]
    if any(not isinstance(value, str) or value not in _CHECK_STATUSES for value in statuses):
        return "UNKNOWN"
    for candidate in ("FAIL", "UNKNOWN", "NOT_RUN"):
        if candidate in statuses:
            return candidate
    return "PASS"


def _sum_budgets(values: Any) -> dict[str, int | float]:
    """Sum observed budget counters from independently fetched Job ledgers."""
    totals: dict[str, int | float] = {
        "logical_calls": 0,
        "http_attempts": 0,
        "tool_calls": 0,
        "charged_tokens": 0,
        "wall_seconds": 0.0,
    }
    for item in values:
        if not isinstance(item, dict):
            continue
        for key in ("logical_calls", "http_attempts", "tool_calls", "charged_tokens"):
            value = item.get(key)
            if type(value) is int and value >= 0:
                totals[key] += value
        wall_seconds = item.get("wall_time_seconds")
        if (
            type(wall_seconds) in {int, float}
            and _finite_number(wall_seconds)
            and wall_seconds >= 0
        ):
            totals["wall_seconds"] += wall_seconds
    return totals


def _consistent_applied_config(evidence: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return actual applied settings only when all observed Jobs agree."""
    configs = [
        item.get("applied_config")
        for item in evidence
        if isinstance(item.get("applied_config"), dict)
    ]
    if not configs or any(item != configs[0] for item in configs[1:]):
        return None
    return configs[0]


def _execution_mode(evidence: list[dict[str, Any]]) -> str:
    """Report one observed execution mode, or mark disagreement unavailable."""
    modes = {
        item.get("execution_mode")
        for item in evidence
        if isinstance(item.get("execution_mode"), str)
    }
    return next(iter(modes)) if len(modes) == 1 else "unavailable"
