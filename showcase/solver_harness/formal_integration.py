"""Public persistence adapter for an explicitly enabled formal backend.

The Lean producer is authoritative for formal acceptance and grades. This module
only assigns attempt identities, validates echo-bound identity, keeps append-only
history, and projects a JSON-safe record through the existing Solver state.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

FORMAL_STATE_VERSION = "formal-verification-v1"
FORMAL_STATUSES = frozenset({
    "disabled", "unsupported", "unavailable", "not_verified", "partial",
    "timeout", "error", "failed", "unknown", "solved",
})
FORMAL_GRADES = frozenset({"L2", "L3"})


class FormalIntegrationError(ValueError):
    """Raised when the product layer cannot preserve a formal receipt."""

    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


@dataclass(frozen=True)
class FormalIntegrationState:
    job_id: str
    run_id: str
    problem: str
    problem_spec: Mapping[str, Any]
    policy: Mapping[str, Any]
    target: Mapping[str, Any]


def _json_copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")))
    except (TypeError, ValueError) as exc:
        raise FormalIntegrationError("formal_receipt_not_json_safe") from exc


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _policy_disabled(policy: Mapping[str, Any] | None) -> bool:
    return not isinstance(policy, Mapping) or policy.get("enabled") is not True


def _initial(policy: Mapping[str, Any]) -> dict[str, Any]:
    frozen = _json_copy(dict(policy))
    return {
        "schema_version": FORMAL_STATE_VERSION,
        "policy": frozen,
        "policy_hash": _digest(frozen),
        "current_attempt_id": None,
        "attempts": [],
        "lineage": {"parent_attempt_id": None, "attempt_ids": [],
                    "total_cost": {"elapsed_seconds": 0.0, "output_bytes": 0}},
        "status": "disabled" if _policy_disabled(policy) else "not_verified",
        "grade": None,
        "current": None,
    }


def _record_for_public(state: Mapping[str, Any]) -> dict[str, Any]:
    record = _json_copy(dict(state))
    current = record.get("current")
    if isinstance(current, Mapping):
        proof = current.get("proof_artifact")
        if isinstance(proof, Mapping):
            logs = proof.get("logs")
            if isinstance(logs, Mapping):
                proof = dict(proof)
                proof["logs"] = {
                    key: (value[:12000] if isinstance(value, str) else value)
                    for key, value in logs.items()
                }
                record["current"] = {**current, "proof_artifact": proof}
    return record


def run_formal_verification(
    state: FormalIntegrationState,
    *,
    backend: Any,
    target: Mapping[str, Any],
    existing: Mapping[str, Any] | None = None,
    review: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one attempt. An existing non-disabled record is returned unchanged."""
    record = _record_for_public(existing) if existing is not None else _initial(state.policy)
    if _policy_disabled(state.policy):
        return _record_for_public(_initial(state.policy))
    current = record.get("current")
    if isinstance(current, Mapping) and current.get("status") != "disabled":
        return record
    attempt = _attempt(state, backend, target, parent_attempt_id=None,
                       review=review, sequence=1)
    record["current_attempt_id"] = attempt["attempt_id"]
    record["attempts"] = [attempt]
    record["current"] = attempt
    record["status"] = attempt["status"]
    record["grade"] = attempt["grade"]
    record["lineage"] = {
        "parent_attempt_id": None,
        "attempt_ids": [attempt["attempt_id"]],
        "total_cost": attempt["cost"],
    }
    return _record_for_public(record)


def reserve_formal_retry(
    state: FormalIntegrationState,
    *,
    existing: Mapping[str, Any],
    expected_attempt_id: str,
    operation: str,
    backend: Any,
    requested_backend: str | None = None,
    allowed_backends: list[str] | tuple[str, ...] | None = None,
    attempt_id: str | None = None,
) -> dict[str, Any]:
    """Create a persisted child attempt for an explicit retry or switch."""
    record = _record_for_public(existing)
    if record.get("current_attempt_id") != expected_attempt_id:
        raise FormalIntegrationError("explicit_current_attempt_required")
    current = record.get("current")
    if not isinstance(current, Mapping) or current.get("status") == "dispatched":
        raise FormalIntegrationError("formal_attempt_not_terminal")
    if operation not in {"retry", "switch"}:
        raise FormalIntegrationError("explicit_retry_or_switch_required")
    if operation == "switch":
        allowed = list(allowed_backends or state.policy.get("allowed_backends") or [])
        if requested_backend not in allowed:
            raise FormalIntegrationError("formal_backend_unsupported")
        if requested_backend == current.get(
            "backend", state.policy.get("backend", state.policy.get("requested_backend"))
        ):
            raise FormalIntegrationError("formal_backend_switch_unchanged")
        backend_name = requested_backend
    else:
        backend_name = state.policy.get("backend", state.policy.get("requested_backend"))
    if getattr(backend, "name", None) != backend_name:
        raise FormalIntegrationError("formal_backend_unavailable")
    attempt_id = attempt_id or f"formal_{uuid.uuid4().hex}"
    attempt = {
        "schema_version": 1,
        "status": "dispatched",
        "grade": None,
        "attempt_id": attempt_id,
        "parent_attempt_id": expected_attempt_id,
        "reason": None,
        "proof_artifact": None,
        "specifications": {},
        "cost": {"elapsed_seconds": 0.0, "output_bytes": 0, "usage": {}, "unknown": False},
        "lineage": {"attempt_id": attempt_id, "parent_attempt_id": expected_attempt_id,
                    "sequence": len(record.get("attempts", [])) + 1},
        "requested_operation": operation,
        "backend": backend_name,
    }
    record["attempts"] = [*record.get("attempts", []), attempt]
    record["current_attempt_id"] = attempt_id
    record["current"] = attempt
    record["status"] = "dispatched"
    record["grade"] = None
    record["lineage"] = {
        **(record.get("lineage") or {}),
        "parent_attempt_id": expected_attempt_id,
        "attempt_ids": [item["attempt_id"] for item in record["attempts"]],
    }
    return _record_for_public(record)


def execute_reserved_attempt(
    state: FormalIntegrationState,
    *,
    backend: Any,
    record: Mapping[str, Any],
    budget: Any = None,
    registry: Any = None,
    backend_registry: Any = None,
) -> dict[str, Any]:
    """Execute a persisted dispatch through the registered bounded tool path."""
    from ..run_budget import BudgetExhausted

    current = _record_for_public(record)
    if current.get("status") != "dispatched" or not isinstance(current.get("current"), Mapping):
        return current
    if _policy_disabled(state.policy):
        return mark_inflight_unknown(current)
    timeout_seconds = budget.remaining_seconds() if budget is not None else None
    try:
        child = current.get("current") if isinstance(current.get("current"), Mapping) else {}
        child_lineage = child.get("lineage") if isinstance(child.get("lineage"), Mapping) else {}
        record_lineage = current.get("lineage") if isinstance(current.get("lineage"), Mapping) else {}
        parent_attempt_id = (
            child.get("parent_attempt_id")
            or child_lineage.get("parent_attempt_id")
            or record_lineage.get("parent_attempt_id")
        )
        sequence = int(child_lineage.get("sequence")
                       or record_lineage.get("sequence") or 1)
        result = _attempt(
            state, backend, state.target,
            parent_attempt_id=parent_attempt_id, review=None,
            sequence=sequence,
            reuse_attempt_id=current["current_attempt_id"],
            timeout_seconds=timeout_seconds, registry=registry,
            backend_registry=backend_registry,
            backend_name=child.get("backend"),
        )
    except BudgetExhausted as exc:
        return _complete_reserved(
            current,
            {"status": "unavailable", "grade": None, "reason": str(exc),
             "cost": {"elapsed_seconds": 0.0, "output_bytes": 0, "usage": {},
                      "unknown": False}, "specifications": {}, "proof_artifact": None},
        )
    return _complete_reserved(current, result)


def _aggregate_cost(attempts):
    """Sum each persisted attempt once while preserving unknown history."""
    total = {"elapsed_seconds": 0.0, "output_bytes": 0, "usage": {}, "unknown": False}
    seen = set()
    for attempt in attempts:
        if not isinstance(attempt, Mapping):
            continue
        attempt_id = attempt.get("attempt_id")
        if attempt_id in seen:
            continue
        seen.add(attempt_id)
        cost = attempt.get("cost") if isinstance(attempt.get("cost"), Mapping) else {}
        total["elapsed_seconds"] += float(cost.get("elapsed_seconds", 0) or 0)
        total["output_bytes"] += int(cost.get("output_bytes", 0) or 0)
        total["unknown"] = total["unknown"] or cost.get("unknown") is True
        if isinstance(cost.get("usage"), Mapping):
            for key, value in cost["usage"].items():
                prior = total["usage"].get(key)
                if (isinstance(value, (int, float)) and not isinstance(value, bool)
                        and isinstance(prior, (int, float)) and not isinstance(prior, bool)):
                    total["usage"][key] = prior + value
                else:
                    total["usage"][key] = value
    return total


def _complete_reserved(record: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    value = _record_for_public(record)
    current = dict(value["current"])
    merged = {**current, **dict(result)}
    merged["attempt_id"] = current["attempt_id"]
    merged["parent_attempt_id"] = current.get("parent_attempt_id")
    merged["lineage"] = {**dict(merged.get("lineage") or {}),
                         "attempt_id": current["attempt_id"],
                         "parent_attempt_id": current.get("parent_attempt_id"),
                         "sequence": current.get("lineage", {}).get("sequence", 1)}
    value["attempts"] = [merged if item.get("attempt_id") == current["attempt_id"] else item
                         for item in value.get("attempts", [])]
    value["current"] = merged
    value["status"] = merged["status"]
    value["grade"] = merged.get("grade")
    value["lineage"] = {**dict(value.get("lineage") or {}),
                        "attempt_ids": [item["attempt_id"] for item in value["attempts"]],
                        "total_cost": _aggregate_cost(value["attempts"])}
    return _record_for_public(value)


def retry_formal_verification(
    state: FormalIntegrationState,
    *,
    backend: Any,
    target: Mapping[str, Any],
    expected_attempt_id: str,
    existing: Mapping[str, Any] | None = None,
    operation: str = "retry",
) -> dict[str, Any]:
    """Explicitly create a new child attempt without resetting history."""
    record = _record_for_public(existing) if existing is not None else _initial(state.policy)
    if _policy_disabled(state.policy):
        raise FormalIntegrationError("formal_disabled")
    if record.get("current_attempt_id") != expected_attempt_id:
        raise FormalIntegrationError("explicit_current_attempt_required")
    if operation not in {"retry", "switch"}:
        raise FormalIntegrationError("explicit_retry_or_switch_required")
    attempt = _attempt(state, backend, target, parent_attempt_id=expected_attempt_id,
                       review=None, sequence=len(record["attempts"]) + 1)
    total = _add_cost(record["lineage"]["total_cost"], attempt["cost"])
    record["attempts"].append(attempt)
    record["current_attempt_id"] = attempt["attempt_id"]
    record["current"] = attempt
    record["status"] = attempt["status"]
    record["grade"] = attempt["grade"]
    record["lineage"] = {
        "parent_attempt_id": expected_attempt_id,
        "attempt_ids": [item["attempt_id"] for item in record["attempts"]],
        "total_cost": total,
    }
    return _record_for_public(record)


def canonical_formal_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Stable state patch used by the existing Solver CAS transaction."""
    return _record_for_public(record)


def reserve_formal_attempt(
    state: FormalIntegrationState,
    *,
    existing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist one dispatch identity before any backend or Docker side effect."""
    record = _record_for_public(existing) if existing is not None else _initial(state.policy)
    if record.get("current_attempt_id") is not None:
        return record
    attempt_id = f"formal_{uuid.uuid4().hex}"
    attempt = {
        "schema_version": 1,
        "status": "dispatched",
        "grade": None,
        "attempt_id": attempt_id,
        "parent_attempt_id": None,
        "reason": None,
        "proof_artifact": None,
        "specifications": {},
        "backend": state.policy.get("backend", state.policy.get("requested_backend")),
        "cost": {"elapsed_seconds": 0.0, "output_bytes": 0, "usage": {}, "unknown": False},
        "lineage": {"attempt_id": attempt_id, "parent_attempt_id": None, "sequence": 1},
    }
    record.update(current_attempt_id=attempt_id, attempts=[attempt], current=attempt,
                  status="dispatched", grade=None,
                  lineage={"parent_attempt_id": None, "attempt_ids": [attempt_id],
                           "total_cost": dict(attempt["cost"])})
    return _record_for_public(record)


def mark_inflight_unknown(record: Mapping[str, Any]) -> dict[str, Any]:
    """Close a recovered reservation as unknown without dispatching or rerunning."""
    value = _record_for_public(record)
    current = value.get("current")
    if not isinstance(current, Mapping) or current.get("status") != "dispatched":
        return value
    closed = {**dict(current), "status": "unknown", "grade": None,
              "reason": "recovered_inflight_unknown",
              "cost": {**dict(current.get("cost") or {}), "unknown": True}}
    value["attempts"] = [closed if item.get("attempt_id") == closed["attempt_id"] else item
                         for item in value.get("attempts", [])]
    value["current"] = closed
    value["status"] = "unknown"
    value["grade"] = None
    value["lineage"] = {**dict(value.get("lineage") or {}),
                        "total_cost": _aggregate_cost(value["attempts"])}
    return _record_for_public(value)


def _attempt(state, backend, target, *, parent_attempt_id, review, sequence,
             reuse_attempt_id=None, timeout_seconds=None, registry=None,
             backend_registry=None, backend_name=None):
    from ..formal import normalize_formal_request, serialize_attempt_result
    from ..run_budget import BudgetExhausted

    attempt_id = reuse_attempt_id or f"formal_{uuid.uuid4().hex}"
    if backend_registry is not None:
        requested_policy = dict(state.policy)
        if backend_name is not None:
            requested_policy.update(backend=backend_name, requested_backend=backend_name)
        try:
            backend = backend_registry.select(target, requested_policy)
        except ValueError as exc:
            reason = str(exc)
            return serialize_attempt_result({
                "status": "unsupported" if "target" in reason else "unavailable",
                "grade": None,
                "attempt_id": attempt_id,
                "parent_attempt_id": parent_attempt_id,
                "reason": reason,
                "proof_artifact": None,
                "specifications": {},
                "cost": {"elapsed_seconds": 0.0, "output_bytes": 0,
                         "usage": {}, "unknown": False},
                "lineage": {"parent_attempt_id": parent_attempt_id},
            })
    raw_request = {
        "schema_version": 1,
        "job_id": state.job_id,
        "run_id": state.run_id,
        "attempt_id": attempt_id,
        "parent_attempt_id": parent_attempt_id,
        "problem": {"text": state.problem},
        "specification": dict(state.problem_spec),
        "target": {key: value for key, value in dict(target).items()
                   if not key.startswith("_")},
        "policy": {**dict(state.policy), "backend": backend_name or state.policy.get(
            "backend", state.policy.get("requested_backend")),
            "timeout_seconds": float(timeout_seconds or state.policy.get("timeout_seconds", 30))},
        "cost": {"elapsed_seconds": 0.0, "output_bytes": 0, "usage": {},
                 "unknown": False},
        "review": None,
    }
    try:
        request = normalize_formal_request(raw_request)
    except (TypeError, ValueError) as exc:
        raise FormalIntegrationError(f"formal_request_invalid:{exc}") from exc
    try:
        if registry is not None:
            invocation = registry.invoke(
                backend.name, request, tool_call_id=attempt_id,
            )
            response_value = invocation.value if invocation.status == "success" else None
            invocation_status = (
                invocation.status if invocation.status in FORMAL_STATUSES
                else "unavailable" if invocation.status == "rejected" else "error"
            )
            response = response_value if invocation.status == "success" else {
                "status": invocation_status,
                "grade": None,
                "attempt_id": attempt_id,
                "parent_attempt_id": parent_attempt_id,
                "cost": {"elapsed_seconds": invocation.duration_seconds or 0.0,
                         "output_bytes": 0,
                         "unknown": invocation.status in {"error", "timeout"}},
                "lineage": {}, "proof_artifact": None, "specifications": {},
                "reason": invocation.error_category or invocation.status,
            }
        else:
            response = backend.invoke(request)
    except BudgetExhausted:
        raise
    except TimeoutError:
        response = {
            "status": "timeout", "grade": None, "attempt_id": attempt_id,
            "parent_attempt_id": parent_attempt_id,
            "cost": {"elapsed_seconds": 0.0, "output_bytes": 0, "unknown": True},
        }
    except Exception:  # noqa: BLE001 - a backend failure is an observed formal error
        response = {
            "status": "error", "grade": None, "attempt_id": attempt_id,
            "parent_attempt_id": parent_attempt_id,
            "cost": {"elapsed_seconds": 0.0, "output_bytes": 0, "unknown": True},
        }
    if not isinstance(response, Mapping):
        raise FormalIntegrationError("formal_response_invalid")
    response = dict(response)
    if response.get("attempt_id") != attempt_id or response.get("parent_attempt_id") != parent_attempt_id:
        observed_cost = response.get("cost")
        observed_cost = dict(observed_cost) if isinstance(observed_cost, Mapping) else {}
        response = {
            "status": "unknown", "grade": None, "attempt_id": attempt_id,
            "parent_attempt_id": parent_attempt_id, "reason": "attempt_identity_mismatch",
            "cost": {**observed_cost, "unknown": True}, "lineage": {},
            "proof_artifact": None, "specifications": {},
        }
    try:
        normalized = serialize_attempt_result(response)
    except (TypeError, ValueError):
        response = {
            "status": "error", "grade": None, "attempt_id": attempt_id,
            "parent_attempt_id": parent_attempt_id, "reason": "formal_response_invalid",
            "cost": {"elapsed_seconds": 0.0, "output_bytes": 0, "unknown": True},
        }
        normalized = serialize_attempt_result(response)
    if normalized.get("attempt_id") != attempt_id or normalized.get("parent_attempt_id") != parent_attempt_id:
        raise FormalIntegrationError("attempt_identity_mismatch")
    status = normalized.get("status")
    if status not in FORMAL_STATUSES or status == "disabled":
        normalized.update(status="error", grade=None, reason="formal_status_invalid")
        status = "error"
    grade = normalized.get("grade")
    if grade not in FORMAL_GRADES and grade is not None:
        normalized.update(status="failed", grade=None, reason="formal_grade_invalid")
        grade = None
    if grade is not None:
        verifier = getattr(backend, "verify_result", None)
        try:
            verified_grade = verifier(request, response) if callable(verifier) else None
        except Exception:  # noqa: BLE001 - verification failure must fail closed
            verified_grade = None
        if verified_grade != grade:
            normalized.update(status="failed", grade=None, reason="formal_receipt_unverified")
            grade = None
        elif backend_registry is not None:
            metadata = backend_registry.metadata(backend.name)
            rank = {"L1": 1, "L2": 2, "L3": 3}
            if metadata is None or rank.get(grade, 0) > rank.get(metadata["maximum_grade"], 0):
                normalized.update(status="failed", grade=None, reason="backend_grade_exceeds_registry")
                grade = None
    if normalized.get("status") != "solved" and grade is not None:
        normalized["grade"] = None
        grade = None
    if normalized.get("status") == "solved" and grade is None:
        normalized.update(status="failed", reason="formal_receipt_unverified")
    cost = normalized.get("cost") if isinstance(normalized.get("cost"), Mapping) else {}
    elapsed = cost.get("elapsed_seconds", 0.0)
    output_bytes = cost.get("output_bytes", 0)
    if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or elapsed < 0:
        elapsed = 0.0
    if isinstance(output_bytes, bool) or not isinstance(output_bytes, int) or output_bytes < 0:
        output_bytes = 0
    normalized["cost"] = {"elapsed_seconds": float(elapsed), "output_bytes": output_bytes,
                          "unknown": cost.get("unknown") is True or status == "unknown",
                          **({"usage": dict(cost["usage"])}
                             if isinstance(cost.get("usage"), Mapping) else {})}
    normalized["lineage"] = {**dict(normalized.get("lineage") or {}),
                             "attempt_id": attempt_id,
                             "parent_attempt_id": parent_attempt_id,
                             "sequence": sequence}
    normalized["backend"] = getattr(backend, "name", backend_name or "unknown")
    return _json_copy(normalized)

def _add_cost(left, right):
    return _aggregate_cost(({"attempt_id": "left", "cost": left},
                            {"attempt_id": "right", "cost": right}))


def _formal_state_store(store):
    from .storage import SolverStateStore

    return SolverStateStore(store._connection)


def _formal_request_hash(event, formal_verification):
    encoded = json.dumps({
        "event": event,
        "state_updates": {"formal_verification": formal_verification},
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def commit_formal_retry_reservation(
    store, run_id: str, *, snapshot: Mapping[str, Any], state: FormalIntegrationState,
    existing: Mapping[str, Any], expected_attempt_id: str, operation: str,
    backend: Any, event: Mapping[str, Any], requested_backend: str | None = None,
    transaction_hook_factory=None,
) -> dict[str, Any]:
    """Persist a child attempt and rebase it once after a concurrent Solver event."""
    from .storage import SolverRevisionConflictError

    record = reserve_formal_retry(
        state, existing=existing, expected_attempt_id=expected_attempt_id,
        operation=operation, backend=backend, requested_backend=requested_backend,
    )
    state_store = _formal_state_store(store)
    transaction_hook = (transaction_hook_factory(record)
                        if transaction_hook_factory is not None else None)
    try:
        with store._lock:
            state_store.commit_event(
                run_id, expected_revision=snapshot["state_revision"],
                state_updates={"formal_verification": record}, event=event,
                request_hash=_formal_request_hash(event, record),
                transaction_hook=transaction_hook,
            )
        return record
    except SolverRevisionConflictError:
        with store._lock:
            latest = state_store.get_run(run_id)
        saved = latest["state"].get("formal_verification") if latest else None
        if (latest is None or not isinstance(saved, Mapping)
                or saved.get("current_attempt_id") != expected_attempt_id):
            raise FormalIntegrationError("explicit_current_attempt_required")
        record = reserve_formal_retry(
            state, existing=saved, expected_attempt_id=expected_attempt_id,
            operation=operation, backend=backend, requested_backend=requested_backend,
            attempt_id=record["current_attempt_id"],
        )
        transaction_hook = (transaction_hook_factory(record)
                            if transaction_hook_factory is not None else None)
        try:
            with store._lock:
                state_store.commit_event(
                    run_id, expected_revision=latest["state_revision"],
                    state_updates={"formal_verification": record}, event=event,
                    request_hash=_formal_request_hash(event, record),
                    transaction_hook=transaction_hook,
                )
        except SolverRevisionConflictError as exc:
            raise FormalIntegrationError("formal_revision_conflict") from exc
        return record


def commit_formal_state_with_one_retry(
    store, run_id: str, *, expected_revision: int,
    formal_verification: Mapping[str, Any], event: Mapping[str, Any],
    expected_attempt_id: str, expected_status: str, transaction_hook=None,
) -> dict[str, Any]:
    """Retry a single CAS conflict only while the same persisted attempt owns state."""
    from .storage import SolverRevisionConflictError

    state_store = _formal_state_store(store)
    try:
        with store._lock:
            return state_store.commit_event(
                run_id, expected_revision=expected_revision,
                state_updates={"formal_verification": formal_verification}, event=event,
                request_hash=_formal_request_hash(event, formal_verification),
                transaction_hook=transaction_hook,
            )
    except SolverRevisionConflictError:
        with store._lock:
            latest = state_store.get_run(run_id)
        saved = latest["state"].get("formal_verification") if latest else None
        current = saved.get("current") if isinstance(saved, Mapping) else None
        if (latest is None or not isinstance(saved, Mapping)
                or not isinstance(current, Mapping)
                or saved.get("current_attempt_id") != expected_attempt_id
                or current.get("status") != expected_status):
            raise
        with store._lock:
            return state_store.commit_event(
                run_id, expected_revision=latest["state_revision"],
                state_updates={"formal_verification": formal_verification}, event=event,
                request_hash=_formal_request_hash(event, formal_verification),
                transaction_hook=transaction_hook,
            )


def run_explicit_formal_retry(
    service, job_id: str, *, run_id: str, problem: str, policy: Mapping[str, Any],
    expected_attempt_id: str, operation: str, reserved_attempt_id: str | None = None,
) -> dict[str, Any]:
    """Run one explicit child attempt through the service's frozen store/budget."""
    from ..run_budget import bind_budget

    identity = service.store.job_identity(job_id)
    if (not isinstance(policy, Mapping) or policy.get("enabled") is not True
            or identity.get("formal_policy") != dict(policy)):
        raise FormalIntegrationError("formal_retry_unavailable")
    store = service.store
    state_store = _formal_state_store(store)
    with store._lock:
        current = state_store.get_run(run_id)
    if current is None or not isinstance(current["state"].get("formal_verification"), Mapping):
        raise FormalIntegrationError("formal_retry_unavailable")
    state = FormalIntegrationState(
        job_id=job_id, run_id=run_id, problem=problem,
        problem_spec=current["state"].get("problem_spec", {}), policy=policy,
        target=policy["target"],
    )
    existing = current["state"]["formal_verification"]
    if reserved_attempt_id is not None:
        record = _record_for_public(existing)
        active_attempt = record.get("current")
        if (record.get("current_attempt_id") != reserved_attempt_id
                or record.get("status") != "dispatched"
                or not isinstance(active_attempt, Mapping)
                or active_attempt.get("parent_attempt_id") != expected_attempt_id):
            raise FormalIntegrationError("formal_reserved_attempt_mismatch")
    else:
        record = reserve_formal_retry(
            state, existing=existing, expected_attempt_id=expected_attempt_id,
            operation=operation, backend=getattr(service.star_pipeline, "formal_backend", None),
        )
        commit_formal_state_with_one_retry(
            store, run_id,
            expected_revision=current["state_revision"], formal_verification=record,
            event={"event_id": f"formal-{record['current_attempt_id']}-dispatched",
                   "type": "formal_verification_dispatched", "status": "dispatched",
                   "grade": None},
            expected_attempt_id=expected_attempt_id,
            expected_status=str(existing.get("status", "unknown")),
        )
    budget = service.budget_ledger.ensure(
        job_id, service.star_pipeline.budget_for_mode("star_limited"),
    )
    with bind_budget(budget):
        backend_registry = service.star_pipeline.formal_registry
        backend_name = record.get("current", {}).get("backend")
        backend = backend_registry.get(backend_name) if backend_registry is not None else None
        if backend is None:
            raise FormalIntegrationError("formal_backend_unavailable")
        completed = execute_reserved_attempt(
            state, backend=backend, record=record, budget=budget,
            registry=service.star_pipeline.registry, backend_registry=backend_registry,
        )
    with store._lock:
        current = state_store.get_run(run_id)
    if current is None:
        raise FormalIntegrationError("formal_retry_unavailable")
    commit_formal_state_with_one_retry(
        store, run_id,
        expected_revision=current["state_revision"], formal_verification=completed,
        event={"event_id": f"formal-{completed['current_attempt_id']}-{completed['status']}",
               "type": "formal_verification_completed",
               "status": completed["status"], "grade": completed["grade"]},
        expected_attempt_id=completed["current_attempt_id"], expected_status="dispatched",
    )
    budget_snapshot = service.budget_ledger.snapshot(job_id)
    return {"record": completed, "budget": budget_snapshot}


def project_formal_verification(state: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Return the persisted formal record without re-reading or re-grading it."""
    value = state.get("formal_verification") if isinstance(state, Mapping) else None
    return value if isinstance(value, Mapping) else None


def project_formal_progress(*, problem: str, problem_spec: Mapping[str, Any],
                            policy: Mapping[str, Any], backend: Any,
                            target: Mapping[str, Any]) -> dict[str, Any]:
    state = FormalIntegrationState("job", "run", problem, problem_spec, policy, target)
    return run_formal_verification(state, backend=backend, target=target)
