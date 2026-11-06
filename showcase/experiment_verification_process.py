"""Project public process evidence and classify natural multistep coverage."""

from __future__ import annotations

import re
from typing import Any

from .experiment_verification_reporting import _safe_nonnegative_int
from .experiment_verification_state import _check

_EVENT_TYPES = {"call_audit", "tool_receipt", "initial_plan_generated", "plan_replaced"}
_PUBLIC_CALL_ID = re.compile(r"solver_call_[0-9a-f]{32}\Z")
_SAFE_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}\Z")
_PUBLIC_ROLES = {
    "explore", "explore_polish", "planner", "reasoner", "reason_noncoding", "researcher",
    "step_verifier", "final_generator", "whole_solution_verifier", "meta", "meta_strategist",
}


def _safe_solver_events(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep public run, plan, call, and receipt relationships from the timeline."""
    timeline = evidence.get("timeline")
    if not isinstance(timeline, list):
        return []
    output = []
    for item in timeline:
        if not isinstance(item, dict) or item.get("solver_event_type") not in _EVENT_TYPES:
            continue
        run_id = item.get("run_id", item.get("job_id"))
        event = {
            "type": item["solver_event_type"],
            "run_id": run_id if isinstance(run_id, str) else None,
            "revision": _safe_nonnegative_int(item.get("solver_revision")),
            "plan_version": _safe_nonnegative_int(item.get("plan_version")),
            "attempt_index": _safe_nonnegative_int(item.get("attempt_index")),
        }
        role = item.get("role")
        if isinstance(role, str) and role in _PUBLIC_ROLES:
            event["role"] = role
        if event["type"] == "call_audit":
            status = item.get("call_status")
            event["status"] = (
                "completed" if status == "completed"
                else "failed" if status in {"failed", "error"}
                else "unknown" if status in {"unknown", "unknown_outcome"}
                else "unavailable"
            )
            call_id = item.get("solver_call_id")
            if isinstance(call_id, str) and _PUBLIC_CALL_ID.fullmatch(call_id):
                event["call_id"] = call_id
            receipts = item.get("consumed_receipt_ids")
            if isinstance(receipts, list) and all(
                isinstance(value, str) and _SAFE_REFERENCE.fullmatch(value)
                for value in receipts
            ):
                event["consumed_receipt_ids"] = receipts
        elif event["type"] == "tool_receipt":
            receipt_id = item.get("receipt_id")
            if isinstance(receipt_id, str) and _SAFE_REFERENCE.fullmatch(receipt_id):
                event["receipt_id"] = receipt_id
            status = item.get("receipt_status")
            event["status"] = status if status in {"success", "failed", "unknown"} else "unavailable"
            if type(item.get("receipt_executed")) is bool:
                event["executed"] = item["receipt_executed"]
        output.append(event)
    return output


def _successful_call(event: dict[str, Any], attempts: list[Any], run_id: Any,
                     allowed_roles: set[str]) -> bool:
    """Bind a completed event to a successful observed public HTTP attempt."""
    if (
        event.get("type") != "call_audit"
        or event.get("status") != "completed"
        or event.get("run_id") != run_id
        or event.get("role") not in allowed_roles
        or not isinstance(event.get("call_id"), str)
    ):
        return False
    return any(
        isinstance(item, dict)
        and item.get("run_id") == run_id
        and item.get("status") == "success"
        and item.get("dispatch_status") == "transport_observed"
        and item.get("role") == event["role"]
        and item.get("solver_call_id") == event["call_id"]
        for item in attempts
    )


def _planner_call_for_plan(events: list[dict[str, Any]], attempts: list[Any], run_id: Any,
                           allowed_roles: set[str], plan_version: int | None) -> dict[str, Any] | None:
    """Bind the current plan to the completed Planner call immediately before its creation."""
    plan_events = [
        item for item in events
        if item.get("type") in {"initial_plan_generated", "plan_replaced"}
        and item.get("run_id") == run_id
        and item.get("plan_version") == plan_version
        and type(item.get("revision")) is int
    ]
    if not plan_events:
        return None
    plan_event = max(plan_events, key=lambda item: item["revision"])
    planner_calls = [
        item for item in events
        if item.get("type") == "call_audit"
        and item.get("role") == "planner"
        and type(item.get("revision")) is int
        and item["revision"] < plan_event["revision"]
        and _successful_call(item, attempts, run_id, allowed_roles)
    ]
    return max(planner_calls, key=lambda item: item["revision"]) if planner_calls else None


def _verified_receipts(events: list[dict[str, Any]], attempts: list[Any], run_id: Any,
                       allowed_roles: set[str], tool_calls: int | None) -> tuple[int | None, bool]:
    """Require each receipt to be consumed by a later successful call in its plan attempt."""
    receipts = [item for item in events if item.get("type") == "tool_receipt"]
    if tool_calls == 0:
        return (0, False) if not receipts else (None, True)
    if tool_calls is None:
        return None, False
    if len(receipts) != tool_calls:
        return None, False
    ids = [item.get("receipt_id") for item in receipts]
    if any(not isinstance(value, str) for value in ids) or len(ids) != len(set(ids)):
        return None, False
    for receipt in receipts:
        revision = receipt.get("revision")
        if (
            receipt.get("run_id") != run_id
            or type(receipt.get("plan_version")) is not int
            or type(receipt.get("attempt_index")) is not int
            or receipt.get("status") != "success"
            or receipt.get("executed") is not True
            or type(revision) is not int
        ):
            return None, False
        if not any(
            _successful_call(event, attempts, run_id, allowed_roles)
            and event.get("plan_version") == receipt.get("plan_version")
            and event.get("attempt_index") == receipt.get("attempt_index")
            and type(event.get("revision")) is int
            and event["revision"] > revision
            and receipt["receipt_id"] in event.get("consumed_receipt_ids", [])
            for event in events
        ):
            return None, False
    return len(receipts), False


def _safe_process_path(
    evidence: dict[str, Any], attempts: list[Any], allowed_roles: set[str], evidence_kind: str
) -> dict[str, Any]:
    """Project current plan progress and relationships from public evidence only."""
    solver_pack = evidence.get("solver")
    solver = solver_pack.get("solver") if isinstance(solver_pack, dict) else None
    progress = solver.get("progress") if isinstance(solver, dict) else None
    progress = progress if isinstance(progress, dict) else None
    budget = evidence.get("budget")
    review = evidence.get("verification")
    history = review.get("history") if isinstance(review, dict) else None
    latest = history[-1] if isinstance(history, list) and history else None
    source = latest.get("source") if isinstance(latest, dict) else None
    events = _safe_solver_events(evidence)
    run_id = evidence.get("evidence_id")
    plan_events = [item for item in events if item["type"] in {"initial_plan_generated", "plan_replaced"}]
    plan_version = _safe_nonnegative_int(progress.get("plan_version")) if progress else None
    attempt_index = _safe_nonnegative_int(progress.get("attempt_index")) if progress else None
    plan_observed = type(plan_version) is int and plan_version > 0
    if type(plan_version) is not int and plan_events:
        versions = [item["plan_version"] for item in plan_events if type(item["plan_version"]) is int]
        plan_version = max(versions) if versions else None
    plan_observed = plan_observed or bool(plan_events)
    planning_roles = {"planner", "reasoner", "reason_noncoding", "step_verifier"}
    planning_attempt_observed = any(
        isinstance(item, dict)
        and item.get("role") in planning_roles
        and item.get("status") in {"success", "error", "unknown"}
        and item.get("dispatch_status") != "not_submitted"
        for item in attempts
    )
    started = plan_observed or planning_attempt_observed
    successful_roles = sorted({
        event["role"] for event in events
        if event.get("plan_version") == plan_version
        and event.get("attempt_index") == attempt_index
        and _successful_call(event, attempts, run_id, allowed_roles)
    })
    planner_event = _planner_call_for_plan(events, attempts, run_id, allowed_roles, plan_version)
    if planner_event is not None:
        successful_roles = sorted(set(successful_roles) | {"planner"})
    steps = progress.get("steps") if progress else None
    reported = (
        sum(isinstance(step, dict) and step.get("reported") is True for step in steps)
        if isinstance(steps, list) else None
    )
    accepted = (
        sum(
            isinstance(step, dict) and step.get("reported") is True
            and step.get("verdict") == "ACCEPT" and step.get("valid") is True
            for step in steps
        )
        if isinstance(steps, list) else None
    )
    tool_calls = _safe_nonnegative_int(budget.get("tool_calls")) if isinstance(budget, dict) else None
    verified, receipt_conflict = _verified_receipts(events, attempts, run_id, allowed_roles, tool_calls)
    return {
        "evidence_kind": evidence_kind,
        "progress_available": progress is not None,
        "execution_started": started,
        "plan_observed": plan_observed,
        "plan_version": plan_version,
        "attempt_index": attempt_index,
        "planned_steps": len(steps) if isinstance(steps, list) else None,
        "reported_steps": reported,
        "accepted_steps": accepted,
        "successful_roles": successful_roles,
        "review_plan_version": (
            _safe_nonnegative_int(source.get("plan_version")) if isinstance(source, dict) else None
        ),
        "review_attempt_index": (
            _safe_nonnegative_int(source.get("attempt_index")) if isinstance(source, dict) else None
        ),
        "review_origin": (
            source.get("origin")
            if isinstance(source, dict) and source.get("origin") in allowed_roles else None
        ),
        "tool_calls": tool_calls,
        "verified_tool_calls": verified,
        "receipt_conflict": receipt_conflict,
    }


def _check_process_path(
    sample: dict[str, Any], safe_evidence: dict[str, Any],
    task: dict[str, Any], transport: dict[str, Any],
) -> dict[str, Any]:
    """Count only a complete, naturally observed provider-live path as coverage."""
    if sample.get("type") != "multistep":
        return _check("PASS", "natural_multistep_not_required")
    process = safe_evidence.get("process_path")
    if not isinstance(process, dict):
        return _check("UNKNOWN", "solver_progress_unavailable")
    started = process.get("execution_started") is True or (
        type(process.get("plan_version")) is int and process["plan_version"] > 0
    )
    if not started:
        return (
            _check("NOT_RUN", "natural_multistep_path_not_observed")
            if task.get("status") == "PASS"
            else _check("UNKNOWN", "solver_progress_unavailable")
        )
    plan_observed = process.get("plan_observed") is True or (
        type(process.get("plan_version")) is int and process["plan_version"] > 0
    )
    if not plan_observed:
        return _check("UNKNOWN", "solver_progress_unavailable")
    if process.get("evidence_kind") != "provider_live" or safe_evidence.get("execution_mode") != "live":
        return _check("NOT_RUN", "provider_live_trace_required")
    version, attempt = process.get("plan_version"), process.get("attempt_index")
    planned, reported, accepted = (
        process.get("planned_steps"), process.get("reported_steps"), process.get("accepted_steps")
    )
    if any(type(value) is not int for value in (version, attempt, planned, reported, accepted)):
        return _check("FAIL", "natural_multistep_trace_incomplete")
    if version <= 0 or attempt < 0 or planned <= 0 or reported != planned or accepted != planned:
        return _check("FAIL", "natural_multistep_trace_incomplete")
    roles = set(process.get("successful_roles", []))
    if not (
        {"planner", "step_verifier", "final_generator"} <= roles
        and roles.intersection({"reasoner", "reason_noncoding"})
    ):
        return _check("FAIL", "natural_multistep_trace_incomplete")
    if process.get("receipt_conflict") is True:
        return _check("FAIL", "tool_receipt_count_mismatch")
    if process.get("verified_tool_calls") is None:
        return _check("UNKNOWN", "tool_receipt_consumption_unverified")
    if task.get("status") == "FAIL":
        return _check("FAIL", "natural_multistep_delivery_failed")
    if task.get("status") == "UNKNOWN":
        return _check("UNKNOWN", "natural_multistep_delivery_unknown")
    if (
        process.get("review_origin") != "final_generator"
        or process.get("review_plan_version") != version
        or process.get("review_attempt_index") != attempt
    ):
        return _check("FAIL", "final_delivery_plan_mismatch")
    if transport.get("status") != "PASS":
        return _check("UNKNOWN", "provider_live_transport_unverified")
    if task.get("status") != "PASS":
        return _check("FAIL", "natural_multistep_delivery_failed")
    return _check("PASS", "natural_multistep_path_observed")
