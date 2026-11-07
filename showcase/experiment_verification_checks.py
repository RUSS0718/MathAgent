"""Verify public Job, attempt, transport, task, and usage projections."""

from __future__ import annotations

import json
from typing import Any

from .experiment_transport_projection import known_transport_rejection
from .experiment_verification_process import _check_process_path, _safe_process_path
from .experiment_verification_reporting import _safe_evidence
from .experiment_verification_state import _CHECKS, _check, _finite_number
from .run_budget import public_solver_call_id

_USAGE_FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens")


def _verify_job(
    manifest: dict[str, Any],
    sample: dict[str, Any],
    record: dict[str, Any],
    job: dict[str, Any],
    report: dict[str, Any],
    evidence: dict[str, Any],
    lookup: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Cross-check public identities, actual applied settings, review, and usage."""
    result = job.get("result")
    result = result if isinstance(result, dict) else {}
    attempts = result.get("request_attempts")
    budget = result.get("budget")
    report_body = report.get("report")
    evidence_run = evidence.get("run")
    if (
        not isinstance(attempts, list)
        or not isinstance(budget, dict)
        or not isinstance(report_body, dict)
    ):
        unknown = {name: _check("UNKNOWN", "job_report_incomplete") for name in _CHECKS}
        return unknown, _safe_evidence(
            sample,
            record,
            job,
            report,
            evidence,
            attempts,
            budget,
            manifest["model"]["name"],
            {item["call_id"] for item in manifest["transport"]["calls"]},
            manifest["evidence_kind"],
        ), {}

    usage = _check_usage(manifest, record, attempts, budget, report_body, evidence, lookup)
    transport = _check_transport(manifest, attempts, lookup.get("transport_identity"))
    evidence_solver = evidence.get("solver")
    evidence_transport = (
        evidence_solver.get("transport_identity") if isinstance(evidence_solver, dict) else None
    )
    if evidence_transport is not None and evidence_transport != lookup.get("transport_identity"):
        transport = _check("FAIL", "transport_projection_mismatch")
    task = _check_task(manifest, record, job, report, report_body, evidence, attempts)
    job_status = job.get("status")
    report_status = report.get("status")
    if report.get("evidence_id") != record["job_id"]:
        task = _check("FAIL", "job_report_identity_mismatch")
    elif not isinstance(job_status, str) or not isinstance(report_status, str):
        if task["status"] != "FAIL":
            task = _check("UNKNOWN", "job_status_unavailable")
    elif report_status != job_status and task["status"] != "FAIL":
        terminal_statuses = {"succeeded", "failed", "canceled"}
        if job_status in terminal_statuses and report_status in terminal_statuses:
            task = _check("FAIL", "job_report_status_mismatch")
        else:
            task = _check("UNKNOWN", "job_status_snapshot_changed")
    if (
        lookup.get("budget") != budget
        or evidence.get("budget") != budget
        or report_body.get("budget") != budget
    ):
        usage = _check("FAIL", "budget_projection_mismatch")
    if (
        budget.get("deadline_at") != record.get("deadline_at")
        or budget.get("limits") != manifest["run_limits"]
    ):
        usage = _check("FAIL", "budget_identity_mismatch")
    if not isinstance(evidence_run, dict) or evidence_run.get("run_id") != record["job_id"]:
        task = _check("FAIL", "evidence_identity_mismatch")
    if evidence.get("evidence_id") != record["job_id"]:
        task = _check("FAIL", "evidence_identity_mismatch")
    if job.get("job_id") != record["job_id"] or job.get("session_id") != record["session_id"]:
        task = _check("FAIL", "job_record_identity_mismatch")
    if lookup.get("status") != job_status and task["status"] != "FAIL":
        task = _check("UNKNOWN", "job_status_snapshot_changed")

    applied = _applied_config(manifest["model"], attempts, job)
    if applied["status"] == "FAIL":
        task = _check("FAIL", "applied_config_mismatch")
    elif applied["status"] != "PASS" and task["status"] == "PASS":
        task = _check("UNKNOWN", "applied_config_unavailable")
    safe = _safe_evidence(
        sample,
        record,
        job,
        report,
        evidence,
        attempts,
        budget,
        manifest["model"]["name"],
        {item["call_id"] for item in manifest["transport"]["calls"]},
        manifest["evidence_kind"],
    )
    safe["applied_config"] = applied["config"] if applied["status"] == "PASS" else None
    safe["process_path"] = _safe_process_path(
        evidence,
        attempts,
        {item["call_id"] for item in manifest["transport"]["calls"]},
        manifest["evidence_kind"],
    )
    return (
        {
            "transport": transport,
            "task": task,
            "usage": usage,
            "coverage": _check("PASS", "sample_audited"),
            "process_path": _check_process_path(sample, safe, task, transport),
        },
        safe,
        budget,
    )


def _check_transport(
    manifest: dict[str, Any], attempts: list[Any], observed: Any
) -> dict[str, Any]:
    """Verify each recorded call against its frozen transport/profile identity."""
    expected = manifest["transport"]
    if not isinstance(observed, dict) or not isinstance(observed.get("calls"), list):
        return _check("UNKNOWN", "transport_identity_unavailable")
    if (
        observed.get("policy") != expected["policy"]
        or observed.get("profile_set_fingerprint") != expected["profile_set_fingerprint"]
    ):
        return _check("FAIL", "transport_policy_mismatch")
    if "rejection" in observed:
        if known_transport_rejection(observed) and observed["rejection"]["role"] in {
            call["call_id"] for call in expected["calls"]
        }:
            return _check("FAIL", "transport_policy_rejected")
        return _check("FAIL", "transport_rejection_invalid")
    calls = observed["calls"]
    if not calls or any(not isinstance(item, dict) for item in calls + attempts):
        return _check("FAIL", "transport_calls_mismatch")
    roles = [item.get("role") for item in calls]
    attempt_roles = [item.get("role") for item in attempts]
    call_ids = [item.get("call_id") for item in calls]
    attempt_call_ids = [item.get("solver_call_id") for item in attempts]
    if (
        any(not isinstance(value, str) for value in roles + attempt_roles)
        or any(not isinstance(value, str) for value in call_ids + attempt_call_ids)
    ):
        return _check("FAIL", "transport_calls_mismatch")
    call_roles = dict(zip(call_ids, roles, strict=True))
    if (
        set(roles) != set(attempt_roles)
        or len(call_ids) != len(set(call_ids))
        or set(call_ids) != set(attempt_call_ids)
        or any(
            item.get("role") != call_roles.get(item.get("solver_call_id"))
            for item in attempts
        )
    ):
        return _check("FAIL", "transport_calls_mismatch")
    allowed = {item["call_id"]: item for item in expected["calls"]}
    for call in calls:
        frozen = allowed.get(call["role"])
        if frozen is None:
            return _check("FAIL", "transport_calls_mismatch")
        if expected["policy"] == "legacy":
            evidence_kind = call.get("evidence_kind")
            if any(
                call.get(key) != frozen.get(key)
                for key in ("transport", "reason", "capability_limit")
            ) or (evidence_kind is not None and not isinstance(evidence_kind, str)):
                return _check("FAIL", "legacy_transport_mismatch")
            if evidence_kind not in {None, "documented"}:
                return _check("FAIL", "legacy_transport_evidence_mismatch")
        else:
            evidence_kind = call.get("evidence_kind")
            if (
                call.get("transport") != "stream"
                or call.get("profile_fingerprint") not in frozen.get(
                    "profile_fingerprints", [frozen.get("profile_fingerprint")]
                )
                or not isinstance(evidence_kind, str)
                or evidence_kind not in {"controlled_test", "provider_live"}
                or (
                    manifest["evidence_kind"] == "provider_live"
                    and evidence_kind != "provider_live"
                )
            ):
                return _check("FAIL", "stream_transport_mismatch")
    return _check("PASS", "transport_matches_manifest")


def _check_task(
    manifest: dict[str, Any],
    record: dict[str, Any],
    job: dict[str, Any],
    report: dict[str, Any],
    report_body: dict[str, Any],
    evidence: dict[str, Any],
    attempts: list[Any],
) -> dict[str, Any]:
    """Require a succeeded Job and an audited whole-review artifact binding."""
    job_status = job.get("status")
    if not isinstance(job_status, str):
        return _check("UNKNOWN", "job_status_unavailable")
    if job_status in {"failed", "canceled"}:
        return _check("FAIL", "job_failed_or_canceled")
    if job_status != "succeeded":
        return _check("UNKNOWN", "job_not_terminal")
    run = evidence.get("run")
    verification = evidence.get("verification")
    semantics = evidence.get("semantics")
    history = verification.get("history") if isinstance(verification, dict) else None
    if (
        not isinstance(run, dict)
        or not isinstance(verification, dict)
        or not isinstance(semantics, dict)
        or not isinstance(history, list)
        or not history
    ):
        return _check("UNKNOWN", "whole_review_unavailable")
    latest = history[-1]
    source = latest.get("source") if isinstance(latest, dict) else None
    findings = latest.get("findings") if isinstance(latest, dict) else None
    if not isinstance(findings, list) or any(not isinstance(item, str) for item in findings):
        return _check("UNKNOWN", "whole_review_unavailable")
    answer = run.get("final_response")
    if not isinstance(answer, str) or not isinstance(source, dict):
        return _check("UNKNOWN", "final_artifact_unavailable")
    if not isinstance(source.get("call_id"), str) or not source["call_id"]:
        return _check("UNKNOWN", "whole_review_source_unavailable")
    from .final_evidence import artifact_identity

    artifact = artifact_identity(answer)
    report_answer = report_body.get("answer")
    if not isinstance(report_answer, str):
        return _check("UNKNOWN", "report_artifact_unavailable")
    if artifact_identity(report_answer) != artifact:
        return _check("FAIL", "report_artifact_binding_mismatch")
    review_attempt_id = public_solver_call_id(record["job_id"], source.get("call_id"))
    review_attempts = [
        item
        for item in attempts
        if isinstance(item, dict)
        and item.get("solver_call_id") == review_attempt_id
        and item.get("role") == "whole_solution_verifier"
    ]
    matching_review = any(
        item.get("status") == "success" for item in review_attempts
    )
    accepted = (
        job.get("verification_mode") == manifest["model"]["verification_mode"]
        and isinstance(job.get("result"), dict)
        and job["result"].get("solver_mode") == manifest["model"]["solver_mode"]
        and report.get("status") == "succeeded"
        and report.get("evidence_id") == record["job_id"]
        and run.get("run_id") == record["job_id"]
        and run.get("status") == "COMPLETED"
        and semantics.get("execution") == "completed"
        and semantics.get("whole_review") == "accepted"
        and semantics.get("binding") == "same_artifact"
        and verification.get("binding") == "same_artifact"
        and isinstance(report_body.get("checks"), dict)
        and report_body["checks"] == verification
        and latest.get("scope") == "whole_solution_llm_review"
        and latest.get("checker_version") == "star-whole-review-v1"
        and any(tag in findings for tag in ("llm_whole_review_accept", "llm_whole_review_accepted"))
        and latest.get("artifact") == artifact
        and source.get("run_id") == record["job_id"]
        and source.get("candidate_version") == len(history)
        and matching_review
    )
    if not accepted:
        if any(item.get("status") == "error" for item in review_attempts):
            return _check("FAIL", "whole_review_attempt_failed")
        if (
            verification.get("binding") == "artifact_changed"
            or semantics.get("whole_review") == "rejected"
        ):
            return _check("FAIL", "whole_review_or_binding_failed")
        return _check("UNKNOWN", "whole_review_or_binding_unverified")
    return _check("PASS", "whole_review_bound_to_delivery")


def _check_usage(
    manifest: dict[str, Any],
    record: dict[str, Any],
    attempts: list[Any],
    budget: dict[str, Any],
    report: dict[str, Any],
    evidence: dict[str, Any],
    lookup: dict[str, Any],
) -> dict[str, Any]:
    """Recompute attempt and provider-usage counters against the public ledger."""
    if report.get("request_attempts") != attempts or evidence.get("request_attempts") != attempts:
        return _check("FAIL", "attempt_projection_mismatch")
    if any(not isinstance(item, dict) for item in attempts):
        return _check("FAIL", "attempt_projection_invalid")
    attempt_ids = [item.get("attempt_id") for item in attempts]
    if any(not isinstance(value, str) or not value for value in attempt_ids) or len(
        attempt_ids
    ) != len(set(attempt_ids)):
        return _check("FAIL", "attempt_identity_mismatch")
    if budget.get("http_attempts") != len(attempts):
        return _check("FAIL", "attempt_count_mismatch")
    logical_ids = [item.get("logical_call_id") for item in attempts]
    if (
        any(not isinstance(value, str) or not value for value in logical_ids)
        or type(budget.get("logical_calls")) is not int
        or budget["logical_calls"] != len(set(logical_ids))
    ):
        return _check("FAIL", "logical_call_count_mismatch")
    logical_call_ids: dict[str, str] = {}
    solver_call_ids: dict[str, str] = {}
    attempts_by_call: dict[str, list[dict[str, Any]]] = {}
    for item in attempts:
        logical_id = item["logical_call_id"]
        solver_call_id = item.get("solver_call_id")
        if not isinstance(solver_call_id, str) or not solver_call_id:
            return _check("FAIL", "attempt_identity_mismatch")
        if (
            (logical_id in logical_call_ids and logical_call_ids[logical_id] != solver_call_id)
            or (solver_call_id in solver_call_ids and solver_call_ids[solver_call_id] != logical_id)
        ):
            return _check("FAIL", "attempt_identity_mismatch")
        logical_call_ids[logical_id] = solver_call_id
        solver_call_ids[solver_call_id] = logical_id
        attempts_by_call.setdefault(solver_call_id, []).append(item)
    for group in attempts_by_call.values():
        indexes = [item.get("attempt_index") for item in group]
        if (
            any(type(index) is not int or index < 1 for index in indexes)
            or len(indexes) != len(set(indexes))
            or sorted(indexes) != list(range(1, len(indexes) + 1))
            or len(group) > manifest["model"]["retry"] + 1
        ):
            return _check("FAIL", "attempt_identity_mismatch")
        dispatch = [item.get("dispatch_status") for item in group]
        statuses = [item.get("status") for item in group]
        if any(
            not isinstance(value, str)
            or value not in {"transport_observed", "not_submitted", "reserved_dispatch_unconfirmed"}
            for value in dispatch
        ):
            return _check("FAIL", "dispatch_status_invalid")
        if any(
            not isinstance(value, str)
            or value not in {"success", "error", "unknown", "not_submitted", "pending", "reserved"}
            for value in statuses
        ):
            return _check("FAIL", "attempt_status_invalid")
        if any(
            (state == "success" and observed != "transport_observed")
            or (
                observed == "not_submitted"
                and state not in {"not_submitted", "error"}
            )
            or (state == "not_submitted" and observed != "not_submitted")
            for observed, state in zip(dispatch, statuses, strict=True)
        ):
            return _check("FAIL", "dispatch_status_mismatch")
        if any(state not in {"error", "not_submitted"} for state in statuses[:-1]):
            return _check("FAIL", "attempt_retry_order_mismatch")
        if "reserved_dispatch_unconfirmed" in dispatch:
            return _check("UNKNOWN", "dispatch_unconfirmed")
    provider_known = budget.get("provider_known")
    unknown_fields = budget.get("provider_unknown_fields")
    if not isinstance(provider_known, dict) or not isinstance(unknown_fields, dict):
        return _check("UNKNOWN", "provider_usage_unavailable")
    unknown_attempts = 0
    for field in _USAGE_FIELDS:
        values = []
        for item in attempts:
            item_usage = item.get("usage")
            if item_usage is not None and not isinstance(item_usage, dict):
                return _check("FAIL", "provider_usage_invalid")
            value = item_usage.get(field) if isinstance(item_usage, dict) else None
            if value is not None and (type(value) is not int or value < 0):
                return _check("FAIL", "provider_usage_invalid")
            values.append(value)
        missing = sum(value is None for value in values)
        known_sum = sum(value for value in values if value is not None)
        expected_known = None if values and missing == len(values) else known_sum
        actual_known = provider_known.get(field)
        if actual_known is not None and (type(actual_known) is not int or actual_known < 0):
            return _check("FAIL", "provider_usage_counter_invalid")
        if (
            type(unknown_fields.get(field)) is not int
            or unknown_fields[field] < 0
            or actual_known != expected_known
            or unknown_fields[field] != missing
        ):
            return _check("FAIL", "provider_usage_counter_mismatch")
    unknown_attempts = sum(
        any(
            item.get("usage") is None or item["usage"].get(field) is None
            for field in _USAGE_FIELDS
        )
        for item in attempts
    )
    if budget.get("unknown_attempts") != unknown_attempts:
        return _check("FAIL", "unknown_attempt_count_mismatch")
    unresolved = sum(
        item.get("status") in {"reserved", "pending", "error", "unknown"}
        for item in attempts
        if isinstance(item, dict)
    )
    if budget.get("unresolved_attempts") != unresolved:
        return _check("FAIL", "unresolved_attempt_count_mismatch")
    if budget.get("limits") != manifest["run_limits"] or budget.get("deadline_at") != record.get(
        "deadline_at"
    ):
        return _check("FAIL", "budget_identity_mismatch")
    if lookup.get("budget") != budget:
        return _check("FAIL", "lookup_budget_mismatch")
    if any(
        type(budget.get(key)) is not int or budget[key] < 0
        for key in ("tool_calls", "charged_tokens", "reserved_tokens")
    ):
        return _check("FAIL", "budget_counter_invalid")
    wall_seconds = budget.get("wall_time_seconds")
    if (
        type(wall_seconds) not in {int, float}
        or not _finite_number(wall_seconds)
        or wall_seconds < 0
    ):
        return _check("FAIL", "budget_counter_invalid")
    if (
        budget.get("unknown_tool_calls") != 0
        or budget.get("unknown_attempts") != 0
        or budget.get("unresolved_attempts") != 0
        or budget.get("reserved_tokens") != 0
    ):
        return _check("UNKNOWN", "usage_unresolved")
    used = {
        "max_model_calls": budget["logical_calls"],
        "max_http_attempts": budget["http_attempts"],
        "max_tool_calls": budget["tool_calls"],
        "max_tokens": budget["charged_tokens"],
    }
    if any(used[key] > manifest["run_limits"][key] for key in used):
        return _check("FAIL", "run_budget_exceeded")
    return _check("PASS", "usage_reconciled")


def _applied_config(
    model: dict[str, Any], attempts: list[Any], job: dict[str, Any]
) -> dict[str, Any]:
    """Derive the applied settings from attempts, not from the runner snapshot."""
    if not attempts:
        return {"status": "NOT_RUN", "config": None}
    values = {
        "name": [item.get("requested_model") for item in attempts if isinstance(item, dict)],
        "thinking_mode": [item.get("thinking_mode") for item in attempts if isinstance(item, dict)],
        "temperature": [item.get("temperature") for item in attempts if isinstance(item, dict)],
        "max_output_tokens": [
            item.get("max_tokens") for item in attempts if isinstance(item, dict)
        ],
        "request_timeout_seconds": [
            item.get("requests_timeout_seconds") for item in attempts if isinstance(item, dict)
        ],
        "retry": [item.get("retry_limit") for item in attempts if isinstance(item, dict)],
        "solver_mode": [(job.get("result") or {}).get("solver_mode")],
        "verification_mode": [job.get("verification_mode")],
    }
    actual = {
        key: fields[0]
        for key, fields in values.items()
        if fields and all(value == fields[0] for value in fields)
    }
    if any(not fields or len(set(map(json.dumps, fields))) != 1 for fields in values.values()):
        return {"status": "FAIL", "config": actual}
    if actual != model:
        return {"status": "FAIL", "config": actual}
    return {"status": "PASS", "config": actual}
