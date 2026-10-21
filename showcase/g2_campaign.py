"""Serial Workspace orchestration and sanitized G2 protocol report builder."""

from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Mapping
from typing import Any

from .g2_live_gate import (
    G2_CASES,
    G2_CLIENT_TIMEOUT_SECONDS,
    G2_DATASET_VERSION,
    G2_MAX_GENERATIONS_PER_RUN,
    G2_MAX_HTTP_ATTEMPTS,
    G2_MAX_TOKENS_PER_ATTEMPT,
    G2_MODEL,
    G2_PROTOCOL_PROMPT_VERSION,
    G2_REPEATS,
    G2_RUN_TIMEOUT_SECONDS,
    G2Case,
    g2_protocol_schema_sha256,
)


def run_g2_campaign(
    client: Any,
    *,
    execution_source: str = "fake_http",
    poll_interval_seconds: float = 0.1,
    run_timeout_seconds: float = G2_RUN_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run the six fixed Workspace Jobs serially and return only public evidence fields."""

    if execution_source not in {"provider_live", "fake_http"}:
        raise ValueError("g2_execution_source_invalid")
    provider_live = execution_source == "provider_live"
    rows: list[dict[str, Any]] = []
    protocol_schema_sha256 = g2_protocol_schema_sha256()
    auth = client.get("/api/check_auth")
    csrf = _json_payload(auth).get("csrf_token")
    session = client.post("/api/new_chat", headers={"X-CSRF-Token": csrf or ""})
    session_id = _json_payload(session).get("new_session_id")
    stopped_reason: str | None = None
    http_attempt_count = 0

    for case in G2_CASES:
        for repeat in range(1, G2_REPEATS + 1):
            row = _new_run_row(
                case,
                repeat,
                execution_source=execution_source,
                protocol_schema_sha256=protocol_schema_sha256,
            )
            if stopped_reason:
                row.update(
                    mode="unavailable",
                    status="blocked",
                    protocol_evidence="blocked",
                    error_category="prior_run_requires_stop",
                )
                rows.append(row)
                continue
            if not session_id:
                row.update(
                    mode="unavailable",
                    status="blocked",
                    protocol_evidence="blocked",
                    error_category="workspace_unavailable",
                )
                rows.append(row)
                stopped_reason = "workspace_unavailable"
                continue
            if http_attempt_count >= G2_MAX_HTTP_ATTEMPTS:
                row.update(
                    mode="unavailable",
                    status="blocked",
                    protocol_evidence="blocked",
                    error_category="campaign_attempt_budget_exhausted",
                )
                rows.append(row)
                stopped_reason = "campaign_attempt_budget_exhausted"
                continue

            headers = {
                "X-CSRF-Token": str(csrf or ""),
                "Idempotency-Key": str(uuid.uuid4()),
            }
            created = client.post(
                "/api/agent/jobs",
                json={
                    "message": case.problem,
                    "session_id": session_id,
                    "verification_mode": "auto",
                    "web_search_enabled": False,
                },
                headers=headers,
            )
            accepted = _json_payload(created)
            run_id = accepted.get("job_id")
            row["run_id"] = run_id if isinstance(run_id, str) else None
            if not run_id or created.status_code not in {200, 202}:
                row.update(
                    status="failed",
                    protocol_evidence="needs_review",
                    error_category=_safe_error(accepted.get("error"), "job_create_failed"),
                )
                rows.append(row)
                continue

            deadline = time.monotonic() + max(0.1, run_timeout_seconds)
            job = {}
            while time.monotonic() < deadline:
                job_response = client.get(f"/api/agent/jobs/{run_id}")
                job = _json_payload(job_response)
                if job.get("status") in {"succeeded", "failed", "canceled"}:
                    break
                time.sleep(max(0.001, poll_interval_seconds))
            timed_out = job.get("status") not in {"succeeded", "failed", "canceled"}
            job_report_response = client.get(f"/api/agent/jobs/{run_id}/report")
            run_snapshot_response = client.get(f"/api/runs/{run_id}")
            run_report_response = client.get(f"/api/runs/{run_id}/report")
            evidence_response = client.get(f"/api/runs/{run_id}/evidence")
            job_report = _json_payload(job_report_response)
            run_snapshot = _json_payload(run_snapshot_response)
            run_report = _json_payload(run_report_response)
            evidence = _json_payload(evidence_response)
            row.update(
                _run_evidence_summary(
                    run_id, job, job_report, run_snapshot, run_report, evidence
                )
            )
            run_error = run_snapshot.get("error")
            attempt_report_issue = _attempt_report_issue(
                run_id,
                job_report_response,
                job_report,
                run_report_response,
                run_report,
                pre_request_configuration=(
                    isinstance(run_error, Mapping)
                    and run_error.get("category") == "configuration"
                    and _tool_summaries(job_report) == []
                    and _tool_summaries(run_report) == []
                ),
            )
            row["status"] = "unknown" if timed_out else str(job.get("status", "failed"))
            if timed_out:
                row["attempts_complete"] = False
                row["error_category"] = "workspace_run_timeout"
            elif attempt_report_issue:
                row["attempts_complete"] = False
                if not row["error_category"]:
                    row["error_category"] = attempt_report_issue
            protocol_passed = _protocol_evidence_passes(row)
            row["protocol_evidence"] = (
                ("pass" if provider_live else "simulated")
                if protocol_passed
                else "needs_review"
            )
            rows.append(row)
            http_attempt_count += len(row["attempts"])
            if timed_out or attempt_report_issue or _requires_stop(row):
                stopped_reason = row.get("error_category") or "workspace_run_unresolved"

    http_attempt_count = sum(len(row["attempts"]) for row in rows)
    if all(_protocol_evidence_passes(row) for row in rows):
        contract_result = "pass"
    elif any(_authentication_stop(row) for row in rows):
        contract_result = "blocked"
    elif any(row["protocol_evidence"] == "needs_review" for row in rows):
        contract_result = "needs_review"
    elif any(row["protocol_evidence"] == "blocked" for row in rows):
        contract_result = "blocked"
    else:
        contract_result = "needs_review"
    attempts_complete = all(row["attempts_complete"] for row in rows)
    if http_attempt_count > G2_MAX_HTTP_ATTEMPTS or not attempts_complete:
        contract_result = "needs_review"
    status = contract_result if provider_live else "simulated"
    return {
        "schema_version": "g2-live-report-v1",
        "gate": "protocol_evidence",
        "mode": "live" if provider_live else "fake",
        "execution_source": execution_source,
        "status": status,
        "contract_result": contract_result,
        "dataset_version": G2_DATASET_VERSION,
        "protocol_prompt_version": G2_PROTOCOL_PROMPT_VERSION,
        "protocol_schema_sha256": protocol_schema_sha256,
        "requested_model": G2_MODEL,
        "run_count": len(rows),
        "executed_run_count": sum(row["run_id"] is not None for row in rows),
        "http_attempt_count": http_attempt_count if attempts_complete else None,
        "known_http_attempt_count": http_attempt_count if attempts_complete else None,
        "attempts_complete": attempts_complete,
        "budget": {
            "max_runs": len(G2_CASES) * G2_REPEATS,
            "max_http_attempts": G2_MAX_HTTP_ATTEMPTS,
            "max_generations_per_run": G2_MAX_GENERATIONS_PER_RUN,
            "attempts_per_generation": 1,
            "max_tokens_per_attempt": G2_MAX_TOKENS_PER_ATTEMPT,
            "thinking_mode": True,
            "retry_total_attempts": 1,
            "client_timeout_seconds": G2_CLIENT_TIMEOUT_SECONDS,
            "run_timeout_seconds": run_timeout_seconds,
            "serial": True,
        },
        "limitations": [
            "只记录原生工具请求、注册工具执行、调用 ID 回传与 Run/Evidence 关联。",
            "continuation 响应到达不证明模型语义上使用了工具结果。",
            "本报告不证明数学能力提升、候选集完备性或一般化工具稳定性。",
        ],
        "runs": rows,
    }


def _new_run_row(
    case: G2Case,
    repeat: int,
    *,
    execution_source: str,
    protocol_schema_sha256: str,
) -> dict[str, Any]:
    return {
        "problem_id": case.problem_id,
        "repeat": repeat,
        "input_version": G2_DATASET_VERSION,
        "input_sha256": hashlib.sha256(case.problem.encode("utf-8")).hexdigest(),
        "protocol_prompt_version": G2_PROTOCOL_PROMPT_VERSION,
        "protocol_schema_sha256": protocol_schema_sha256,
        "run_id": None,
        "evidence_id": None,
        "run_evidence_id": None,
        "evidence_pack_id": None,
        "mode": "live" if execution_source == "provider_live" else "fake",
        "execution_source": execution_source,
        "status": "not_started",
        "protocol_evidence": "blocked",
        "attempts": [],
        "attempts_complete": True,
        "finish_reasons": [],
        "tool_call_ids": [],
        "error_category": None,
    }


def _run_evidence_summary(
    run_id: str,
    job: Mapping[str, Any],
    job_report: Mapping[str, Any],
    run_snapshot: Mapping[str, Any],
    run_report: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    job_data = job_report.get("report") if isinstance(job_report.get("report"), Mapping) else {}
    run_data = run_report.get("report") if isinstance(run_report.get("report"), Mapping) else {}
    job_attempts = job_data.get("request_attempts")
    run_attempts = run_data.get("request_attempts")
    valid_attempt_sources = [
        items for items in (job_attempts, run_attempts) if _valid_attempt_list(items, run_id)
    ]
    attempts = max(valid_attempt_sources, key=len, default=[])
    tools = job_data.get("tool_summaries") if isinstance(job_data.get("tool_summaries"), list) else []
    tool = tools[0] if len(tools) == 1 and isinstance(tools[0], Mapping) else {}
    call_id = tool.get("tool_call_id") if isinstance(tool, Mapping) else None
    continuation_id = tool.get("continuation_tool_call_id") if isinstance(tool, Mapping) else None
    evidence_tools = evidence.get("tools") if isinstance(evidence.get("tools"), list) else []
    error = run_snapshot.get("error")
    category = error.get("category") if isinstance(error, Mapping) else None
    if not category:
        category = job.get("error") or tool.get("error_category")
    report_checks = job_data.get("checks")
    evidence_checks = evidence.get("verification")
    return {
        "run_id": run_id,
        "evidence_id": job_report.get("evidence_id"),
        "run_evidence_id": run_report.get("evidence_id"),
        "evidence_pack_id": evidence.get("evidence_id"),
        "workspace_mode": job_report.get("mode", run_snapshot.get("execution_mode", "unavailable")),
        "attempts": [dict(item) for item in attempts if isinstance(item, Mapping)],
        "finish_reasons": [item.get("finish_reason") for item in attempts if isinstance(item, Mapping)],
        "requested_models": [item.get("requested_model") for item in attempts if isinstance(item, Mapping)],
        "returned_models": [item.get("returned_model") for item in attempts if isinstance(item, Mapping)],
        "tool_protocol": tool.get("protocol") if isinstance(tool, Mapping) else None,
        "tool_name": tool.get("name") if isinstance(tool, Mapping) else None,
        "tool_execution_status": tool.get("status") if isinstance(tool, Mapping) else None,
        "checker_candidate_status": tool.get("candidate_status") if isinstance(tool, Mapping) else None,
        "checker_evidence_id": tool.get("checker_evidence_id") if isinstance(tool, Mapping) else None,
        "tool_call_id": call_id,
        "continuation_tool_call_id": continuation_id,
        "tool_call_ids": [
            item.get("tool_call_id") for item in tools
            if isinstance(item, Mapping) and isinstance(item.get("tool_call_id"), str)
        ],
        "continuation_response_received": (
            tool.get("continuation_response_received") is True if isinstance(tool, Mapping) else False
        ),
        "continuation_status": tool.get("continuation_status") if isinstance(tool, Mapping) else None,
        "evidence_trace_matches": (
            job_report.get("evidence_id") == run_id
            and run_report.get("evidence_id") == run_id
            and evidence.get("evidence_id") == run_id
            and tools == run_data.get("tool_summaries", [])
            and tools == evidence_tools
            and report_checks == evidence_checks
            and attempts == run_data.get("request_attempts", [])
        ),
        "run_status": run_snapshot.get("status"),
        "error_category": _safe_error(category, ""),
    }


def _tool_summaries(report: Mapping[str, Any]) -> Any:
    data = report.get("report")
    return data.get("tool_summaries") if isinstance(data, Mapping) else None


def _protocol_evidence_passes(row: Mapping[str, Any]) -> bool:
    attempts = row.get("attempts")
    if (
        row.get("attempts_complete") is not True
        or not isinstance(attempts, list)
        or len(attempts) != G2_MAX_GENERATIONS_PER_RUN
    ):
        return False
    if any(
        not isinstance(attempt, Mapping)
        or attempt.get("status") != "success"
        or attempt.get("requested_model") != G2_MODEL
        or attempt.get("thinking_mode") is not True
        or not isinstance(attempt.get("max_tokens"), int)
        or not 1 <= attempt["max_tokens"] <= G2_MAX_TOKENS_PER_ATTEMPT
        for attempt in attempts
    ):
        return False
    if [attempt.get("finish_reason") for attempt in attempts] != ["tool_calls", "stop"]:
        return False
    return all((
        row.get("status") == "succeeded",
        row.get("workspace_mode") == "live",
        row.get("run_status") == "COMPLETED",
        row.get("evidence_trace_matches") is True,
        row.get("tool_protocol") == "native",
        row.get("tool_name") == "polynomial_check",
        row.get("tool_execution_status") == "success",
        bool(row.get("checker_evidence_id")),
        bool(row.get("tool_call_id")),
        row.get("tool_call_id") == row.get("continuation_tool_call_id"),
        row.get("continuation_response_received") is True,
        row.get("continuation_status") == "response_received",
    ))


def _requires_stop(row: Mapping[str, Any]) -> bool:
    if row.get("error_category") in {
        "configuration",
        "tool_schema_invalid",
        "attempt_report_unavailable",
        "attempt_report_malformed",
    }:
        return True
    return any(
        isinstance(attempt, Mapping) and attempt.get("http_status") in {401, 402, 403, 429}
        for attempt in row.get("attempts", [])
    )


def _authentication_stop(row: Mapping[str, Any]) -> bool:
    return row.get("error_category") == "configuration" or any(
        isinstance(attempt, Mapping) and attempt.get("http_status") in {401, 402, 403, 429}
        for attempt in row.get("attempts", [])
    )


def _attempt_report_issue(
    run_id: str,
    job_response: Any,
    job_report: Mapping[str, Any],
    run_response: Any,
    run_report: Mapping[str, Any],
    *,
    pre_request_configuration: bool = False,
) -> str | None:
    if getattr(job_response, "status_code", None) != 200 or getattr(run_response, "status_code", None) != 200:
        return "attempt_report_unavailable"
    job_data = job_report.get("report")
    run_data = run_report.get("report")
    if not isinstance(job_data, Mapping) or not isinstance(run_data, Mapping):
        return "attempt_report_unavailable"
    job_attempts = job_data.get("request_attempts")
    run_attempts = run_data.get("request_attempts")
    if not isinstance(job_attempts, list) or not isinstance(run_attempts, list):
        return "attempt_report_unavailable"
    if job_attempts != run_attempts:
        return "attempt_report_malformed"
    if not job_attempts and pre_request_configuration:
        return None
    if not _valid_attempt_list(job_attempts, run_id):
        return "attempt_report_malformed"
    return None


def _valid_attempt_list(attempts: Any, run_id: str) -> bool:
    return isinstance(attempts, list) and bool(attempts) and all(
        _valid_attempt(item, run_id) for item in attempts
    )


def _valid_attempt(attempt: Any, run_id: str) -> bool:
    return (
        isinstance(attempt, Mapping)
        and attempt.get("run_id") == run_id
        and isinstance(attempt.get("attempt_id"), str)
        and bool(attempt.get("attempt_id"))
        and type(attempt.get("attempt_index")) is int
        and attempt.get("attempt_index", 0) > 0
        and attempt.get("status") in {"success", "error"}
        and isinstance(attempt.get("requested_model"), str)
        and type(attempt.get("max_tokens")) is int
    )


def _json_payload(response: Any) -> dict[str, Any]:
    value = response.get_json(silent=True)
    return value if isinstance(value, dict) else {}


def _safe_error(value: Any, default: str) -> str:
    if isinstance(value, str) and value and value.replace("_", "").isalnum():
        return value[:80]
    return default


__all__ = ["run_g2_campaign"]
