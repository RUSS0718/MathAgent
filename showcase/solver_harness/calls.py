"""Opt-in call audit, partial streams and explicitly controlled retries."""

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime

from ..redaction import redact
from ..run_budget import public_solver_call_id
from .intern_port import KNOWN_PROTOCOL_FAILURES


class CallInterrupted(BaseException):
    """Stop role normalization while preserving a recoverable public snapshot."""

    def __init__(self, run_id, call_id=None):
        self.run_id = run_id
        self.call_id = call_id


def pending_call(run):
    """Return the audited action whose owning math commit has not happened."""
    calls = run["state"].get("calls", {})
    if not calls:
        return None
    record = max(calls.values(), key=lambda item: item["request_revision"])
    audit = {
        "call_audit", "call_activity", "session_recorded", "call_retry_authorized",
        "session_started", "transport_selected", "transport_rejected",
    }
    if any(event["state_revision"] > record["request_revision"]
           and event["type"] not in audit for event in run["events"]):
        return None
    return record


def latest_retry_id(calls, call_id):
    """Resolve an immutable retry lineage without changing the original call."""
    for _ in range(len(calls)):
        successor = next((item for item in calls.values()
                          if retry_parent_id(item) == call_id), None)
        if successor is None:
            break
        call_id = successor["call_id"]
    return call_id


def retry_parent_id(record):
    """Return the private lineage ID while accepting older persisted records."""
    return record.get("retry_of_internal", record.get("retry_of"))


def _save(harness, run, record, *, status=None, event_type="call_audit", event_fields=None,
          state_updates=None):
    latest = harness.get_run(run["run_id"])
    updates = {"calls": {**latest["state"].get("calls", {}), record["call_id"]: redact(record)}}
    updates.update(state_updates or {})
    if status is not None and latest["state"]["phase"] != "TERMINAL":
        updates["status"] = status
    updated = harness._commit_event(
        run["run_id"],
        expected_revision=latest["state_revision"],
        current=latest,
        event={
            "event_id": f"call-{record['call_id']}-{record['status']}-{latest['state_revision']}",
            "type": event_type,
            "call_id": record["call_id"],
            "outcome": record["status"],
            **(event_fields or {}),
        },
        state_updates=updates,
    )
    run.clear()
    run.update(updated)


def _consume(value, partial, checkpoint):
    if isinstance(value, Mapping):
        return deepcopy(dict(value))
    result = None
    for chunk in value:
        if isinstance(chunk, str):
            partial.append(chunk)
        elif isinstance(chunk, Mapping):
            if chunk.get("type") in {"text_delta", "partial"}:
                partial.append(str(chunk.get("text", "")))
            elif chunk.get("type") == "tool_error":
                error = RuntimeError(str(chunk.get("error", "tool failed")))
                error.tool_error = True
                raise error
            elif isinstance(chunk.get("result"), Mapping):
                result = deepcopy(dict(chunk["result"]))
                if "usage" in chunk:
                    result["usage"] = chunk["usage"]
        checkpoint()
    if result is None:
        raise RuntimeError("stream ended without a completed result")
    return result


def dispatch(harness, run, operation, request, session_dispatch):
    if getattr(harness, "_product_recovery", False):
        pending = pending_call(run)
        if pending is not None:
            if pending["role"] != request["role"]:
                raise ValueError("recovery action owner mismatch")
            request = {**deepcopy(pending["request"]), "problem": request.get("problem")}
    retry = run["state"].get("authorized_retry")
    calls = run["state"].get("calls", {})
    current_id = latest_retry_id(calls, request.get("call_id"))
    if current_id != request.get("call_id"):
        record = calls[current_id]
        request = {**request, "call_id": current_id, "retry_of": retry_parent_id(record)}
    if retry and current_id == retry["call_id"]:
        request = {
            **request,
            "call_id": retry["new_call_id"],
            "retry_of": retry["call_id"],
        }

    def invoke(prepared):
        call_id = prepared.get("call_id")
        if not isinstance(call_id, str) or not call_id.strip():
            raise ValueError("call_id must be a non-empty string")
        if prepared.get("run_id") != run["run_id"]:
            raise ValueError("call run identity mismatch")
        latest = harness.get_run(run["run_id"])
        excluded = {
            "problem",
            "prompt_layers",
            "role_context",
            "session_history",
            "state_revision",
            "session_history_authority",
            "prompt_fingerprint",
            "prompt_layers_fingerprint",
            "schema_fingerprint",
            "input_fingerprint",
            "activity_observer",
        }
        safe_request = {
            key: deepcopy(value) for key, value in prepared.items() if key not in excluded
        }
        identity_hash = hashlib.sha256(
            json.dumps(redact(safe_request), sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        existing = latest["state"].get("calls", {}).get(call_id)
        if existing is not None:
            if (
                existing["role"] != prepared["role"]
                or existing.get("request_hash") != identity_hash
            ):
                raise ValueError("call identity conflict")
            if existing["status"] == "completed":
                return deepcopy(existing["response"])
            raise CallInterrupted(run["run_id"])
        if latest["state"]["phase"] == "TERMINAL":
            raise CallInterrupted(run["run_id"])
        report = prepared.get("report")
        receipts = report.get("tool_receipts", []) if isinstance(report, Mapping) else []
        record = {
            "call_id": call_id,
            "role": prepared["role"],
            "run_id": run["run_id"],
            "plan_version": latest["state"].get("plan_version"),
            "attempt_index": latest["state"].get("attempt_index"),
            "consumed_receipt_ids": [
                receipt["receipt_id"]
                for receipt in receipts
                if isinstance(receipt, Mapping)
                and isinstance(receipt.get("receipt_id"), str)
                and receipt["receipt_id"]
            ] if isinstance(receipts, list) else [],
            "problem_hash": latest["state"]["problem_hash"],
            "config_hash": latest["state"]["config_hash"],
            "session_key": prepared.get("session_key"),
            "request_revision": latest["state_revision"],
            "request": safe_request,
            "request_hash": identity_hash,
            "owner_instance": harness._instance_id,
            "retry_of": (
                public_solver_call_id(run["run_id"], prepared["retry_of"])
                if prepared.get("retry_of")
                else None
            ),
            "status": "dispatched",
            "partial_text": "",
            "usage": None,
        }
        if prepared.get("retry_of"):
            record["retry_of_internal"] = prepared["retry_of"]
        activity_enabled = harness._config.get("features", {}).get("stream_activity") is True
        if activity_enabled:
            record["stream_metrics"] = {
                "status": "dispatched",
                "dispatched_at": datetime.now(UTC).isoformat(),
                "response_headers_at": None,
                "first_event_at": None,
                "first_reasoning_at": None,
                "first_content_at": None,
                "last_content_at": None,
                "last_activity_at": None,
                "completion_at": None,
                "event_count": 0,
                "reasoning_chars": 0,
                "content_bytes": 0,
                "usage_known": False,
            }
        _save(harness, run, record)
        prepared = harness.prepare_request(run, prepared)

        def observe_transport(decision, _request):
            latest = harness.get_run(run["run_id"])
            locked = latest["state"].get("transport_policy")
            choice = {
                "policy": decision.get("policy", "stream_first"),
                "profile_set_fingerprint": decision.get("profile_set_fingerprint"),
            }
            mismatch = locked is not None and (
                locked.get("policy") != choice["policy"]
                or locked.get("profile_set_fingerprint") != choice["profile_set_fingerprint"]
            )
            selected = dict(decision)
            record["transport_decision"] = redact(selected)
            event_type = (
                "transport_rejected"
                if mismatch or selected.get("transport") == "reject"
                else "transport_selected"
            )
            reason = "transport_policy_run_mismatch" if mismatch else decision.get("reason")
            if mismatch:
                selected.update(transport="reject", reason=reason, new_run_required=True)
                record["transport_decision"] = redact(selected)
                record.update(status="policy_rejected", error_category=reason)
            if selected.get("transport") == "reject":
                return not mismatch
            state_updates = {}
            if locked is None:
                state_updates["transport_policy"] = choice
            _save(
                harness, run, record, event_type=event_type,
                event_fields={
                    "transport": selected.get("transport"),
                    "transport_reason": selected.get("reason"),
                    "transport_selection_reason": decision.get("reason") if mismatch else None,
                    "transport_evidence_kind": decision.get("evidence_kind"),
                    "transport_profile_fingerprint": decision.get("profile_fingerprint"),
                    "transport_profile_set_fingerprint": decision.get("profile_set_fingerprint"),
                    "transport_policy": choice["policy"],
                    "new_run_required": selected.get("new_run_required") is True or mismatch,
                },
                state_updates=state_updates,
            )
            return not mismatch

        prepared["transport_decision_observer"] = observe_transport
        if activity_enabled:
            def observe_activity(activity):
                if not isinstance(activity, Mapping):
                    return
                metrics = dict(record["stream_metrics"])
                kind = activity.get("kind")
                at = activity.get("at")
                if not isinstance(at, str) or not at.strip():
                    at = datetime.now(UTC).isoformat()
                metrics["last_activity_at"] = at
                if kind == "response_headers":
                    metrics["response_headers_at"] = metrics["response_headers_at"] or at
                elif kind in {"event", "reasoning", "content", "usage"}:
                    metrics["event_count"] = max(
                        metrics.get("event_count", 0), int(activity.get("event_count", 0) or 0)
                    )
                    if kind == "event" and metrics["first_event_at"] is None:
                        metrics["first_event_at"] = at
                    if kind == "reasoning":
                        metrics["first_reasoning_at"] = metrics["first_reasoning_at"] or at
                    if kind == "content":
                        metrics["first_content_at"] = metrics["first_content_at"] or at
                        metrics["last_content_at"] = at
                    for key in ("reasoning_chars", "content_bytes"):
                        value = activity.get(key)
                        if type(value) is int and value >= 0:
                            metrics[key] = max(metrics.get(key, 0), value)
                    if kind == "usage":
                        metrics["usage_known"] = activity.get("usage_known") is True
                elif kind == "completion":
                    metrics["completion_at"] = at
                    metrics["status"] = "completed"
                    metrics["usage_known"] = activity.get("usage_known") is True
                elif kind in {"disconnect", "cancel", "deadline", "unknown"}:
                    metrics["status"] = "unknown"
                safe_metrics = {key: value for key, value in metrics.items() if key != "text"}
                record["stream_metrics"] = safe_metrics
                _save(
                    harness,
                    run,
                    record,
                    event_type="call_activity",
                    event_fields={"activity_kind": kind or "activity", "stream_activity": safe_metrics},
                )

            prepared["activity_observer"] = observe_activity
        partial = []

        def checkpoint():
            record.update(status="streaming", partial_text="".join(partial))
            _save(harness, run, record)

        try:
            response = _consume(operation(deepcopy(prepared)), partial, checkpoint)
        except Exception as exc:
            if getattr(exc, "no_dispatch", False) is True:
                decision = getattr(exc, "transport_decision", None) or {}
                record.update(
                    status="policy_rejected",
                    error_category=getattr(exc, "category", "transport_policy_rejected"),
                    transport=redact(decision),
                )
                latest = harness.get_run(run["run_id"])
                locked = latest["state"].get("transport_policy")
                state_updates = {}
                if locked is None and decision.get("policy"):
                    state_updates["transport_policy"] = {
                        "policy": decision["policy"],
                        "profile_set_fingerprint": decision.get("profile_set_fingerprint"),
                    }
                _save(
                    harness,
                    run,
                    record,
                    event_type="transport_rejected",
                    event_fields={
                        "transport": decision.get("transport"),
                        "transport_reason": decision.get("reason"),
                        "transport_evidence_kind": decision.get("evidence_kind"),
                        "transport_profile_fingerprint": decision.get("profile_fingerprint"),
                        "transport_profile_set_fingerprint": decision.get("profile_set_fingerprint"),
                        "transport_policy": decision.get("policy"),
                        "new_run_required": decision.get("new_run_required") is True,
                    },
                    state_updates=state_updates,
                )
                raise CallInterrupted(run["run_id"], record["call_id"]) from None
            if getattr(exc, "category", None) == "run_budget_exhausted":
                from .budget import HardBudgetStop, stop

                attempts = getattr(exc, "request_attempts", [])
                record.update(status="unknown_outcome" if attempts else "budget_rejected",
                              error_category="run_budget_exhausted")
                _save(harness, run, record)
                stop(harness, run, "shared_admission_budget_exhausted")
                raise HardBudgetStop(run["run_id"]) from None
            partial.append(str(getattr(exc, "partial_text", "")))
            category = getattr(exc, "category", None)
            # A fully received response that failed JSON/schema validation is a
            # known protocol failure, not an unknown remote outcome: keep the
            # provider finish reason, known usage and a safe response reference.
            known_protocol = category in KNOWN_PROTOCOL_FAILURES
            record.update(
                status="tool_error" if getattr(exc, "tool_error", False)
                else "protocol_failed" if known_protocol else "unknown_outcome",
                partial_text="".join(partial),
                usage=getattr(exc, "usage", None),
                finish_reason=getattr(exc, "finish_reason", None),
                response_excerpt=getattr(exc, "response_excerpt", None),
                error_type=type(exc).__name__,
                error_category=category,
            )
            _save(harness, run, record, status=None if known_protocol else "interrupted")
            raise CallInterrupted(run["run_id"], record["call_id"]) from None
        latest = harness.get_run(run["run_id"])
        if latest["state"]["phase"] == "TERMINAL":
            record.update(
                status="ignored_late_response",
                partial_text="".join(partial),
                usage=response.get("usage"),
            )
            _save(harness, run, record)
            raise CallInterrupted(run["run_id"])
        record.update(
            status="completed",
            response=response,
            partial_text="".join(partial),
            usage=response.get("usage"),
        )
        _save(harness, run, record)
        return response

    result = session_dispatch(harness, run, invoke, request)
    harness._product_recovery = False
    return result


def retry_call(harness, run, problem, decision):
    if not isinstance(decision, Mapping):
        raise ValueError("retry_call must provide call_id and new_call_id")
    old_id, new_id = decision.get("call_id"), decision.get("new_call_id")
    calls = run["state"].get("calls", {})
    old = calls.get(old_id)
    if old is None or old["status"] not in {"unknown_outcome", "tool_error", "dispatched"}:
        raise ValueError("retry requires an interrupted audited call")
    if not isinstance(new_id, str) or not new_id.strip() or new_id == old_id:
        raise ValueError("retry requires a new call_id")
    if new_id in calls:
        if retry_parent_id(calls[new_id]) != old_id:
            raise ValueError("retry call identity conflict")
        return run
    state = run["state"]
    if state["phase"] == "TERMINAL":
        return run
    from .budget import budget_reason

    reason = budget_reason(state, harness._config)
    if reason == "runtime_budget_exhausted":
        raise ValueError("retry runtime budget exhausted")
    if reason:
        raise ValueError("retry model call budget exhausted")
    role = old["role"]
    from .roles import role_operation

    operation = role_operation(harness, role)
    if operation is None:
        raise ValueError("retry role port unavailable")
    reserved = harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={"event_id": f"retry-{new_id}", "type": "call_retry_authorized", "retry_of": old_id},
        state_updates={
            "counters": {**state["counters"], "model_calls": state["counters"]["model_calls"] + 1}
        },
    )
    run.clear()
    run.update(reserved)
    request = {
        **deepcopy(old["request"]),
        "problem": problem,
        "call_id": new_id,
        "retry_of": old_id,
    }
    harness.dispatch(run, operation, request)
    record = deepcopy(run["state"]["calls"][new_id])
    _save(harness, run, record, status="recovered_pending_validation")
    return run


def recover_inflight(harness, run):
    """A prior process cannot prove that an emitted external request completed."""
    abandoned = [
        record
        for record in run["state"].get("calls", {}).values()
        if record["status"] in {"dispatched", "streaming"}
        and record.get("owner_instance") != harness._instance_id
    ]
    if not abandoned:
        return run
    calls = deepcopy(run["state"]["calls"])
    for record in abandoned:
        calls[record["call_id"]].update(status="unknown_outcome", usage=None)
    updates = {"calls": calls}
    if run["state"]["phase"] != "TERMINAL":
        updates["status"] = "interrupted"
    event = {
        "event_id": f"calls-recovered-{run['state_revision']}",
        "type": "call_audit",
        "outcome": "unknown_outcome",
    }
    payload = json.dumps(
        {"event": event, "state_updates": updates},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return harness._state_store.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event=event,
        state_updates=updates,
        request_hash=hashlib.sha256(payload.encode()).hexdigest(),
    )
