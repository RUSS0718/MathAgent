"""Opt-in call audit, partial streams and explicitly controlled retries."""

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy

from ..redaction import redact


class CallInterrupted(BaseException):
    """Stop role normalization while preserving a recoverable public snapshot."""

    def __init__(self, run_id):
        self.run_id = run_id


def pending_call(run):
    """Return the audited action whose owning math commit has not happened."""
    calls = run["state"].get("calls", {})
    if not calls:
        return None
    record = max(calls.values(), key=lambda item: item["request_revision"])
    audit = {"call_audit", "session_recorded", "call_retry_authorized", "session_started"}
    if any(event["state_revision"] > record["request_revision"]
           and event["type"] not in audit for event in run["events"]):
        return None
    return record


def _save(harness, run, record, *, status=None):
    latest = harness.get_run(run["run_id"])
    updates = {"calls": {**latest["state"].get("calls", {}), record["call_id"]: redact(record)}}
    if status is not None and latest["state"]["phase"] != "TERMINAL":
        updates["status"] = status
    updated = harness.commit_event(
        run["run_id"],
        expected_revision=latest["state_revision"],
        event={
            "event_id": f"call-{record['call_id']}-{record['status']}-{latest['state_revision']}",
            "type": "call_audit",
            "call_id": record["call_id"],
            "outcome": record["status"],
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
    current_id = request.get("call_id")
    # Follow immutable retry lineage; every unknown attempt remains in the audit.
    for _ in range(len(calls)):
        successor = next((item for item in calls.values()
                          if item.get("retry_of") == current_id), None)
        if successor is None:
            break
        current_id = successor["call_id"]
    if current_id != request.get("call_id"):
        record = calls[current_id]
        request = {**request, "call_id": current_id, "retry_of": record["retry_of"]}
    if retry and current_id == retry["call_id"]:
        request = {**request, "call_id": retry["new_call_id"], "retry_of": retry["call_id"]}

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
        record = {
            "call_id": call_id,
            "role": prepared["role"],
            "run_id": run["run_id"],
            "problem_hash": latest["state"]["problem_hash"],
            "config_hash": latest["state"]["config_hash"],
            "session_key": prepared.get("session_key"),
            "request_revision": latest["state_revision"],
            "request": safe_request,
            "request_hash": identity_hash,
            "owner_instance": harness._instance_id,
            "retry_of": prepared.get("retry_of"),
            "status": "dispatched",
            "partial_text": "",
            "usage": None,
        }
        _save(harness, run, record)
        prepared = harness.prepare_request(run, prepared)
        partial = []

        def checkpoint():
            record.update(status="streaming", partial_text="".join(partial))
            _save(harness, run, record)

        try:
            response = _consume(operation(deepcopy(prepared)), partial, checkpoint)
        except Exception as exc:
            partial.append(str(getattr(exc, "partial_text", "")))
            record.update(
                status="tool_error" if getattr(exc, "tool_error", False) else "unknown_outcome",
                partial_text="".join(partial),
                usage=getattr(exc, "usage", None),
                error_type=type(exc).__name__,
                error_category=getattr(exc, "category", None),
            )
            _save(harness, run, record, status="interrupted")
            raise CallInterrupted(run["run_id"]) from None
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
        if calls[new_id].get("retry_of") != old_id:
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
    record["retry_of"] = old_id
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
