"""Authorized serial Job execution and same-identity recovery for frozen Runs."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from .experiment_execution_records import record_run_identity
from .experiment_execution_state import (
    is_sha256 as _is_digest,
)
from .experiment_execution_state import (
    load_registered_manifest as _load_registered_manifest,
)
from .experiment_execution_state import (
    read_json_object as _read_json,
)
from .experiment_execution_state import (
    remove_intent as _remove_intent,
)
from .experiment_execution_state import (
    save_execution_status as _save,
)
from .experiment_execution_state import (
    write_json_once as _write_json_once,
)
from .experiment_manifest import is_executable_evidence_kind, validate_manifest
from .experiment_runner import preflight_manifest, read_status, register_run
from .job_events import public_event_summary


def run_batch(
    manifest: Any,
    *,
    expected_sha256: str,
    run_id: str,
    output_root: str | Path = "artifacts/experiments",
    context: dict[str, Any],
) -> dict[str, Any]:
    record = validate_manifest(manifest)
    if not is_executable_evidence_kind(record["evidence_kind"]):
        raise ValueError("experiment_evidence_kind_unavailable")
    if (
        record["evidence_kind"] == "provider_live"
        and record["authorization"]["execution_authorized"] is not True
    ):
        raise ValueError("experiment_live_authorization_required")
    if record["model"]["retry"] not in {0, 1} or (
        record["model"]["retry"] == 1 and record["evidence_kind"] != "provider_live"
    ):
        raise ValueError("experiment_retry_unsupported")
    authorization = context.get("authorization")
    try:
        authorized = authorization.authorize(expected_sha256, record["evidence_kind"], run_id)
    except Exception:
        authorized = False
    if not authorized:
        raise ValueError("experiment_invocation_authorization_required")
    ready = _preflight(record, expected_sha256, context)
    if not ready["ready"]:
        raise ValueError(ready["errors"][0])
    directory = Path(output_root) / run_id
    status = register_run(
        record,
        expected_sha256=expected_sha256,
        run_id=run_id,
        output_root=output_root,
        **_preflight_context(context),
    )
    status.update(
        phase="starting",
        started_at=time.time(),
        deadline_at=time.time() + record["run_limits"]["max_runtime_seconds"],
        current_index=0,
        current_job_id=None,
        current_session_id=None,
        usage=_zero_usage(),
        completed_samples=[],
        run_records=[],
    )
    _save(directory, status)
    adapter = _job_adapter(context)
    _validate_runtime_contract(adapter, record)
    return _advance(record, directory, status, adapter)


def resume_batch(
    run_id: str,
    *,
    expected_sha256: str,
    output_root: str | Path = "artifacts/experiments",
    context: dict[str, Any],
) -> dict[str, Any]:
    status = read_status(run_id, output_root=output_root)
    directory = Path(output_root) / run_id
    manifest = _load_registered_manifest(directory)
    if not is_executable_evidence_kind(manifest["evidence_kind"]):
        raise ValueError("experiment_evidence_kind_unavailable")
    if (
        manifest["evidence_kind"] == "provider_live"
        and manifest["authorization"]["execution_authorized"] is not True
    ):
        raise ValueError("experiment_live_authorization_required")
    if manifest["model"]["retry"] not in {0, 1} or (
        manifest["model"]["retry"] == 1 and manifest["evidence_kind"] != "provider_live"
    ):
        raise ValueError("experiment_retry_unsupported")
    if status["manifest_sha256"] != expected_sha256:
        raise ValueError("experiment_manifest_hash_mismatch")
    authorization = context.get("authorization")
    try:
        authorized = authorization.authorize(expected_sha256, manifest["evidence_kind"], run_id)
    except Exception:
        authorized = False
    if not authorized:
        raise ValueError("experiment_invocation_authorization_required")
    if status.get("phase") in {"completed", "stopped"}:
        return status
    ready = _preflight(manifest, expected_sha256, context)
    if not ready["ready"]:
        return _stop(directory, status, "source_or_config_change")
    if status.get("current_index", 0) < len(manifest["samples"]) and not status.get(
        "current_session_id"
    ):
        return _stop(directory, status, "unknown_session")
    adapter = _job_adapter(context)
    _validate_runtime_contract(adapter, manifest)
    return _advance(manifest, directory, status, adapter, resume=True)


def _preflight(manifest: dict[str, Any], digest: str, context: dict[str, Any]) -> dict[str, Any]:
    return preflight_manifest(
        manifest,
        expected_sha256=digest,
        current_source=context.get("current_source", {}),
        trusted_model_config=context.get("trusted_model_config"),
        server_model_config=context.get("server_model_config"),
        sample_resolver=context.get("sample_resolver"),
        transport_adapter=context.get("transport_adapter"),
    )


def _preflight_context(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "current_source": context.get("current_source", {}),
        "trusted_model_config": context.get("trusted_model_config"),
        "server_model_config": context.get("server_model_config"),
        "sample_resolver": context.get("sample_resolver"),
        "transport_adapter": context.get("transport_adapter"),
    }


def _job_adapter(context: dict[str, Any]) -> Any:
    factory = context.get("job_adapter_factory")
    if not callable(factory):
        raise ValueError("experiment_job_adapter_unavailable")
    return factory()


def _validate_runtime_contract(adapter: Any, manifest: dict[str, Any]) -> None:
    validate = getattr(adapter, "validate_runtime_contract", None)
    if not callable(validate):
        raise ValueError("experiment_runtime_config_unavailable")
    try:
        if validate(manifest) is not True:
            raise ValueError
    except Exception:
        raise ValueError("experiment_runtime_config_mismatch") from None


def _advance(
    manifest: dict[str, Any],
    directory: Path,
    status: dict[str, Any],
    adapter: Any,
    *,
    resume: bool = False,
) -> dict[str, Any]:
    samples = manifest["samples"]
    limits = manifest["run_limits"]
    batch_limits = manifest["batch_limits"]
    while status["current_index"] < len(samples):
        if time.time() >= status["deadline_at"]:
            return _stop(directory, status, "hard_limit")
        intent_path = directory / "dispatch_intent.json"
        has_unresolved_intent = intent_path.exists()
        if _batch_limit_exhausted(status["usage"], batch_limits, completed=status["completed"]) or (
            not status.get("current_job_id")
            and not has_unresolved_intent
            and _batch_reservation_exhausted(status["usage"], limits, batch_limits)
        ):
            return _stop(directory, status, "hard_limit")
        index = status["current_index"]
        sample = samples[index]
        if index in status["completed_samples"]:
            status["current_index"] += 1
            continue
        session_id = status.get("current_session_id")
        if not session_id:
            if resume:
                return _stop(directory, status, "unknown_session")
            try:
                session_id = adapter.create_session(status["run_id"])
            except Exception:
                return _stop(directory, status, "session_creation_unknown")
            if not isinstance(session_id, str) or not session_id:
                return _stop(directory, status, "session_creation_unknown")
            status["current_session_id"] = session_id
            status["phase"] = "dispatching"
            _save(directory, status)
        intent = _read_json(intent_path)
        if intent is None and resume and status.get("current_job_id"):
            return _stop(directory, status, "ledger_or_binding_defect")
        if intent is None:
            key = str(uuid.uuid4())
            deadline_at = min(status["deadline_at"], time.time() + limits["max_runtime_seconds"])
            try:
                digest = adapter.request_digest(
                    sample,
                    session_id,
                    budget_limits=limits,
                    deadline_at=deadline_at,
                )
            except Exception:
                return _stop(directory, status, "request_digest_unavailable")
            if not _is_digest(digest):
                return _stop(directory, status, "request_digest_invalid")
            intent = {
                "index": index,
                "sample_id": sample["id"],
                "session_id": session_id,
                "idempotency_key": key,
                "request_digest": digest,
                "deadline_at": deadline_at,
            }
            _write_json_once(intent_path, intent)
        elif intent.get("index") != index or intent.get("sample_id") != sample["id"]:
            return _stop(directory, status, "ledger_or_binding_defect")

        job_id = status.get("current_job_id")
        if not job_id:
            try:
                existing = adapter.find_by_idempotency_key(
                    intent["idempotency_key"], intent["request_digest"]
                )
            except Exception:
                return _stop(directory, status, "unknown_dispatch")
            if existing:
                if len(existing) != 1 or not _match_lookup(existing[0], intent):
                    return _stop(directory, status, "ledger_or_binding_defect")
                job_id = existing[0]["job_id"]
            else:
                if resume and intent_path.exists():
                    # A durable intent without a known Job may have crossed the POST boundary.
                    # Recovery must stop for review instead of replaying the request.
                    return _stop(directory, status, "unknown_dispatch")
                try:
                    response = adapter.create_job(
                        sample,
                        session_id,
                        intent["idempotency_key"],
                        budget_limits=limits,
                        deadline_at=intent["deadline_at"],
                    )
                except Exception:
                    status["pending_intent"] = intent["idempotency_key"]
                    _save(directory, status)
                    try:
                        existing = adapter.find_by_idempotency_key(
                            intent["idempotency_key"], intent["request_digest"]
                        )
                    except Exception:
                        existing = []
                    if len(existing) != 1 or not _match_lookup(existing[0], intent):
                        return _stop(directory, status, "unknown_dispatch")
                    job_id = existing[0]["job_id"]
                else:
                    job_id = response.get("job_id") if isinstance(response, dict) else None
                    try:
                        existing = adapter.find_by_idempotency_key(
                            intent["idempotency_key"], intent["request_digest"]
                        )
                    except Exception:
                        existing = []
                    if (
                        not isinstance(job_id, str)
                        or len(existing) != 1
                        or not _match_lookup(existing[0], intent)
                        or existing[0].get("job_id") != job_id
                    ):
                        return _stop(directory, status, "ledger_or_binding_defect")
            status["current_job_id"] = job_id
            status["event_cursor"] = 0
            status["phase"] = "running"
        if not record_run_identity(status, intent, job_id=job_id):
            return _stop(directory, status, "ledger_or_binding_defect")
        _save(directory, status)

        if resume and status.get("resume_pending"):
            return _stop(directory, status, "unknown_resume")
        if resume and status.get("phase") == "running":
            try:
                recovery = adapter.resume_preflight(job_id, intent["deadline_at"], intent=intent)
            except Exception:
                return _stop(directory, status, "resume_review_required")
            observer_only = isinstance(recovery, dict) and recovery.get("observer_only") is True
            remote_succeeded = (
                isinstance(recovery, dict) and recovery.get("status") == "succeeded"
            )
            if remote_succeeded:
                if not _observer_attachment_is_safe(recovery, job_id, intent, limits):
                    return _stop(directory, status, "resume_review_required")
            elif observer_only:
                if not _observer_attachment_is_safe(recovery, job_id, intent, limits):
                    return _stop(directory, status, "resume_review_required")
            elif not _resume_is_safe(recovery, intent["deadline_at"]):
                return _stop(directory, status, "resume_review_required")
            else:
                resume_key = status.get("resume_idempotency_key") or str(uuid.uuid4())
                status["resume_idempotency_key"] = resume_key
                status["resume_pending"] = True
                _save(directory, status)
                try:
                    prior = adapter.find_resume_by_idempotency_key(resume_key)
                    if prior:
                        digest = adapter.resume_request_digest(job_id)
                        if len(prior) != 1 or prior[0].get("request_digest") != digest:
                            return _stop(directory, status, "resume_action_ambiguous")
                    else:
                        adapter.resume_job(job_id, resume_key)
                    status["resume_pending"] = False
                    _save(directory, status)
                except Exception:
                    return _stop(directory, status, "unknown_resume")

        def record_progress() -> None:
            if _record_execution_events(status, adapter, job_id):
                _save(directory, status)

        try:
            wait_with_progress = getattr(adapter, "wait_for_job_with_progress", None)
            if callable(wait_with_progress):
                observation = wait_with_progress(
                    job_id,
                    intent["deadline_at"],
                    on_progress=record_progress,
                )
            else:
                observation = adapter.wait_for_job(job_id, intent["deadline_at"])
        except Exception as exc:
            _record_execution_events(status, adapter, job_id)
            observer_error = _safe_observer_error(exc)
            if observer_error is not None:
                status["observer_error"] = observer_error
            return _stop(directory, status, "unknown_job_status")
        _record_execution_events(status, adapter, job_id)
        stop_reason = _observation_stop_reason(
            observation, manifest["transport"], usage_policy=manifest.get("usage_policy", "required")
        )
        if stop_reason:
            status["pending_intent"] = None
            return _stop(directory, status, stop_reason)
        if observation["status"] == "running":
            if time.time() >= intent["deadline_at"]:
                return _stop(directory, status, "hard_limit")
            status["phase"] = "running"
            status["pending_intent"] = None
            _save(directory, status)
            return status
        if observation["status"] != "succeeded":
            return _stop(directory, status, "job_failed_or_canceled")
        usage = _usage(observation["budget"])
        if not _within(usage, limits):
            return _stop(directory, status, "hard_limit")
        status["usage"] = _add_usage(status["usage"], usage)
        status["completed"] += 1
        status["completed_samples"].append(index)
        if not record_run_identity(status, intent, job_id=job_id):
            return _stop(directory, status, "ledger_or_binding_defect")
        status["current_index"] += 1
        status["current_job_id"] = None
        status["current_session_id"] = None
        status["pending_intent"] = None
        status.pop("resume_idempotency_key", None)
        status["phase"] = "running"
        _save(directory, status)
        _remove_intent(intent_path)
        resume = False
    status["phase"] = "completed"
    status["stop_reason"] = None
    _save(directory, status)
    return status


def _observation_stop_reason(
    observation: Any, expected_transport: dict[str, Any], *, usage_policy: str = "required"
) -> str | None:
    if not isinstance(observation, dict):
        return "unknown_job_status"
    if observation.get("ledger_consistent") is not True:
        return "ledger_or_binding_defect"
    if observation.get("transport_rejected") is True:
        return "transport_policy_rejected"
    if observation.get("transport_known") is not True:
        return "unknown_transport"
    if observation.get("transport") != expected_transport:
        return "unknown_transport"
    if observation.get("status") not in {"succeeded", "running"}:
        return "job_failed_or_canceled"
    if _has_unknown(observation.get("budget")):
        metering_only = (
            usage_policy == "observe_only" and observation.get("status") == "succeeded"
            and isinstance(observation.get("budget"), dict)
            and all(observation["budget"].get(key) == 0
                    for key in ("unresolved_attempts", "unknown_tool_calls"))
        )
        if not metering_only:
            return "incomplete_or_unresolved_usage"
    return None


def _resume_is_safe(value: Any, deadline_at: float) -> bool:
    return (
        isinstance(value, dict)
        and value.get("safe_to_resume") is True
        and value.get("unknown_actions") == 0
        and value.get("orphan_tool_actions") == 0
        and value.get("ledger_consistent") is True
        and value.get("deadline_at") == deadline_at
        and time.time() < deadline_at
    )


def _observer_attachment_is_safe(
    value: Any, job_id: str, intent: dict[str, Any], limits: dict[str, Any]
) -> bool:
    if not isinstance(value, dict):
        return False
    budget = value.get("budget")
    return (
        value.get("safe_to_resume") is True
        and value.get("job_id") == job_id
        and value.get("request_digest") == intent.get("request_digest")
        and value.get("status") in {"queued", "running", "succeeded"}
        and value.get("ledger_consistent") is True
        and value.get("deadline_at") == intent.get("deadline_at")
        and isinstance(budget, dict)
        and budget.get("limits") == limits
        and budget.get("deadline_at") == intent.get("deadline_at")
        and not _has_unknown(budget)
        and time.time() < intent["deadline_at"]
    )


def _match_lookup(value: Any, intent: dict[str, Any]) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("job_id"), str)
        and value.get("request_digest") == intent["request_digest"]
    )


def _usage(value: dict[str, Any]) -> dict[str, float | int]:
    return {
        "logical_calls": value["logical_calls"],
        "http_attempts": value["http_attempts"],
        "tool_calls": value["tool_calls"],
        "charged_tokens": value["charged_tokens"],
        "wall_seconds": value["wall_time_seconds"],
    }


def _zero_usage() -> dict[str, float | int]:
    return {
        "logical_calls": 0,
        "http_attempts": 0,
        "tool_calls": 0,
        "charged_tokens": 0,
        "wall_seconds": 0.0,
    }


def _add_usage(
    left: dict[str, float | int], right: dict[str, float | int]
) -> dict[str, float | int]:
    return {key: left[key] + right[key] for key in left}


def _has_unknown(value: Any) -> bool:
    if not isinstance(value, dict):
        return True
    return any(
        value.get(key) != 0
        for key in ("unknown_attempts", "unresolved_attempts", "unknown_tool_calls")
    )


def _within(usage: dict[str, float | int], limits: dict[str, Any], *, batch: bool = False) -> bool:
    mapping = {
        "logical_calls": "logical_calls" if batch else "max_model_calls",
        "http_attempts": "http_attempts" if batch else "max_http_attempts",
        "tool_calls": "tool_calls" if batch else "max_tool_calls",
        "charged_tokens": "charged_tokens" if batch else "max_tokens",
        "wall_seconds": "wall_seconds" if batch else "max_runtime_seconds",
    }
    return all(usage[key] <= limits[limit] for key, limit in mapping.items())


def _batch_limit_exhausted(
    usage: dict[str, float | int],
    limits: dict[str, Any],
    *,
    completed: int = 0,
) -> bool:
    if completed >= limits["runs"]:
        return True
    mapping = {
        "logical_calls": "logical_calls",
        "http_attempts": "http_attempts",
        "tool_calls": "tool_calls",
        "charged_tokens": "charged_tokens",
        "wall_seconds": "wall_seconds",
    }
    return any(usage[key] >= limits[limit] for key, limit in mapping.items())


def _batch_reservation_exhausted(
    usage: dict[str, float | int],
    run_limits: dict[str, Any],
    batch_limits: dict[str, Any],
) -> bool:
    mapping = {
        "logical_calls": ("max_model_calls", "logical_calls"),
        "http_attempts": ("max_http_attempts", "http_attempts"),
        "tool_calls": ("max_tool_calls", "tool_calls"),
        "charged_tokens": ("max_tokens", "charged_tokens"),
        "wall_seconds": ("max_runtime_seconds", "wall_seconds"),
    }
    return any(
        usage[used] + run_limits[per_run] > batch_limits[total]
        for used, (per_run, total) in mapping.items()
    )


def _stop(directory: Path, status: dict[str, Any], reason: str) -> dict[str, Any]:
    status["phase"] = "stopped"
    status["stop_reason"] = reason
    _save(directory, status)
    return status


def _safe_observer_error(error: Exception) -> dict[str, Any] | None:
    code = getattr(error, "code", None)
    if not isinstance(code, str) or not code or not all(
        character.isascii() and (character.isalnum() or character == "_")
        for character in code
    ):
        return None
    result = {"code": code}
    status = getattr(error, "status", None)
    if type(status) is int and 100 <= status <= 599:
        result["http_status"] = status
    return result


def _record_execution_events(status: dict[str, Any], adapter: Any, job_id: str) -> bool:
    read_events = getattr(adapter, "execution_events", None)
    if not callable(read_events):
        return False
    cursor = status.get("event_cursor", 0)
    previous_cursor = cursor
    try:
        events = read_events(job_id, after_id=cursor)
    except Exception:
        return False
    if not isinstance(events, list):
        return False
    tail = status.setdefault("log_tail", [])
    if not isinstance(tail, list):
        tail = status["log_tail"] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_id = event.get("id")
        if type(event_id) is not int or event_id <= cursor:
            continue
        cursor = event_id
        summary = public_event_summary(event)
        if summary is not None:
            tail.append(summary)
    status["event_cursor"] = cursor
    status["log_tail"] = tail[-50:]
    return cursor != previous_cursor
