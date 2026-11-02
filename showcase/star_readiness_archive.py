"""Allowlist projections for immutable #97 experiment archives."""

from collections.abc import Mapping

from llm_response import public_attempt, safe_identifier

from .final_evidence import artifact_identity
from .star_readiness_registration import digest

_BUDGET_FIELDS = (
    "logical_calls", "http_attempts", "tool_calls", "charged_tokens", "reserved_tokens",
    "unknown_attempts", "unresolved_attempts", "unknown_tool_calls",
)
_RECEIPT_FIELDS = (
    "run_id", "status", "image", "exit_code", "executed", "cleanup_verified",
    "receipt_ref", "budget_ref", "sha256", "stdout_sha256", "stderr_sha256",
)
_SEMANTIC_FIELDS = ("transport", "execution", "whole_review", "binding")


def registration_record(manifest):
    """Keep frozen inputs and hashes while omitting the full public question text."""
    record = dict(manifest)
    record["questions"] = [
        {key: question[key] for key in ("id", "source", "text_sha256", "type")}
        for question in manifest["questions"]
    ]
    record["sha256"] = digest(manifest)
    return record


def preflight_record(observed):
    """Persist only the isolated preflight identity, outcome and usage counters."""
    identity = observed.get("identity") if isinstance(observed, Mapping) else None
    receipt = observed.get("receipt") if isinstance(observed, Mapping) else None
    budget = observed.get("budget") if isinstance(observed, Mapping) else None
    summary = {
        "available": observed.get("available") is True if isinstance(observed, Mapping) else False,
        "identity": _pick(identity, ("run_id", "image_id", "receipt_ref", "budget_ref")),
        "receipt": _pick(receipt, _RECEIPT_FIELDS),
        "budget": budget_record(budget),
    }
    reason = observed.get("reason") if isinstance(observed, Mapping) else None
    if reason in {"preflight_failed", "experiment_preflight_evidence_invalid"}:
        summary["reason"] = reason
    return summary


def run_record(bundle, *, job_id):
    """Record public result identity, semantics and metering without raw bodies."""
    job = bundle.get("job") if isinstance(bundle, Mapping) else {}
    report = bundle.get("report") if isinstance(bundle, Mapping) else {}
    evidence = bundle.get("evidence") if isinstance(bundle, Mapping) else {}
    run = bundle.get("run") if isinstance(bundle, Mapping) else {}
    result = job.get("result") if isinstance(job, Mapping) else {}
    answer = result.get("final_response", "") if isinstance(result, Mapping) else ""
    checks = report.get("checks") if isinstance(report, Mapping) else None
    tool_items = evidence.get("tools", []) if isinstance(evidence, Mapping) else []
    evidence_run = evidence.get("run") if isinstance(evidence, Mapping) else None
    report_attempts = report.get("request_attempts", []) if isinstance(report, Mapping) else []
    evidence_attempts = evidence.get("request_attempts", []) if isinstance(evidence, Mapping) else []
    report_answer = report.get("answer") if isinstance(report, Mapping) else None
    answer_identity = {
        "present": bool(answer.strip()) if isinstance(answer, str) else False,
        "sha256": artifact_identity(answer)["sha256"] if isinstance(answer, str) else None,
    }
    return {
        "bundle_invariants": {
            "job_run_identity": job_id == (run.get("run_id") if isinstance(run, Mapping) else None)
            == (evidence_run.get("run_id") if isinstance(evidence_run, Mapping) else None),
            "answer_binding": report_answer == answer,
            "semantics_match": (
                isinstance(report, Mapping) and isinstance(evidence, Mapping)
                and report.get("semantics") == evidence.get("semantics")
            ),
            "verification_match": (
                isinstance(report, Mapping) and isinstance(evidence, Mapping)
                and report.get("checks") == evidence.get("verification")
            ),
            "budget_match": (
                isinstance(report, Mapping) and isinstance(evidence, Mapping)
                and report.get("budget") == evidence.get("budget")
            ),
            "request_attempts_match": report_attempts == evidence_attempts,
        },
        "job": {
            "job_id": safe_identifier(job_id),
            "status": safe_identifier(job.get("status")) if isinstance(job, Mapping) else None,
        },
        "run": _pick(run, ("run_id", "status", "stage")),
        "answer_identity": answer_identity,
        # Scoped bundle checks and LLM review do not independently establish correctness.
        "math_verdict": "unknown",
        "semantics": _semantic_record(report.get("semantics") if isinstance(report, Mapping) else None),
        "budget": budget_record(report.get("budget") if isinstance(report, Mapping) else None),
        "request_attempts": [
            public_attempt(item, run_id=job_id, role=item.get("role"))
            for item in report.get("request_attempts", [])
            if isinstance(item, Mapping)
        ] if isinstance(report, Mapping) else [],
        "verification": {
            "sha256": digest(checks) if checks is not None else None,
            "status": safe_identifier(checks.get("status")) if isinstance(checks, Mapping) else None,
            "finding_count": len(checks.get("findings", []))
            if isinstance(checks, Mapping) and isinstance(checks.get("findings"), list) else None,
        },
        "tools": [_tool_record(item) for item in tool_items if isinstance(item, Mapping)]
        if isinstance(tool_items, list) else [],
        "evidence_identity": {
            "run_id": evidence_run.get("run_id")
            if isinstance(evidence_run, Mapping) else None,
            "request_attempt_count": len(evidence_attempts)
            if isinstance(evidence_attempts, list) else None,
            "verification_sha256": digest(evidence.get("verification"))
            if isinstance(evidence, Mapping) and evidence.get("verification") is not None else None,
        },
    }


def delivery_record(delivery):
    """Retain the review-binding verdict and semantics without candidate text."""
    fields = (
        "runner_version", "review_bound", "proof_delivered", "nonfastpath", "reason",
        "review_call_id", "generator_call_id", "candidate_version", "proof_count",
    )
    record = _pick(delivery, fields)
    record["semantics"] = _semantic_record(
        delivery.get("semantics") if isinstance(delivery, Mapping) else None
    )
    return record


def budget_record(value):
    """Retain only numeric S3 totals and booleans for unknown usage fields."""
    if not isinstance(value, Mapping):
        return None
    result = {
        key: value.get(key) if type(value.get(key)) is int and value[key] >= 0 else None
        for key in _BUDGET_FIELDS
    }
    known = value.get("provider_known")
    result["provider_known"] = {
        key: known.get(key) if type(known.get(key)) is int and known[key] >= 0 else None
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    } if isinstance(known, Mapping) else None
    unknown = value.get("provider_unknown_fields")
    result["provider_unknown_fields"] = {
        safe_identifier(str(key)): bool(item) for key, item in unknown.items()
        if safe_identifier(str(key)) is not None
    } if isinstance(unknown, Mapping) else None
    return result


def _semantic_record(value):
    """Keep only controlled lifecycle labels from the public semantics object."""
    if not isinstance(value, Mapping):
        return None
    return {key: safe_identifier(value.get(key)) for key in _SEMANTIC_FIELDS if key in value}


def _tool_record(value):
    """Retain tool status and fixed-image receipt identity without output content."""
    receipt = value.get("receipt")
    return {
        "name": safe_identifier(value.get("name")),
        "status": safe_identifier(value.get("status")),
        "duration_seconds": value.get("duration_seconds")
        if type(value.get("duration_seconds")) in {int, float} and value["duration_seconds"] >= 0
        else None,
        "receipt": _pick(receipt, _RECEIPT_FIELDS),
    }


def _pick(value, fields):
    """Copy selected scalar fields after removing non-identifier text values."""
    if not isinstance(value, Mapping):
        return None
    result = {}
    for key in fields:
        if key not in value:
            continue
        item = value[key]
        if isinstance(item, str):
            result[key] = safe_identifier(item)
        elif item is None or type(item) in {bool, int, float}:
            result[key] = item
    return result
