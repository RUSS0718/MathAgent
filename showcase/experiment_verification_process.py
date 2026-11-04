"""Project process evidence and classify natural multistep path coverage."""

from __future__ import annotations

from typing import Any

from .experiment_verification_reporting import _safe_nonnegative_int
from .experiment_verification_state import _check


def _safe_process_path(
    evidence: dict[str, Any],
    attempts: list[Any],
    allowed_roles: set[str],
    evidence_kind: str,
) -> dict[str, Any]:
    """Project just the counters and roles needed to audit an observed solver path."""
    solver_pack = evidence.get("solver")
    solver = solver_pack.get("solver") if isinstance(solver_pack, dict) else None
    progress = solver.get("progress") if isinstance(solver, dict) else None
    budget = evidence.get("budget")
    whole_review = evidence.get("verification")
    history = whole_review.get("history") if isinstance(whole_review, dict) else None
    latest = history[-1] if isinstance(history, list) and history else None
    review_source = latest.get("source") if isinstance(latest, dict) else None
    if not isinstance(progress, dict):
        return {
            "evidence_kind": evidence_kind,
            "progress_available": False,
            "plan_version": None,
            "review_plan_version": None,
            "review_origin": None,
            "planned_steps": None,
            "reported_steps": None,
            "accepted_steps": None,
            "successful_roles": [],
            "tool_calls": None,
        }
    steps = progress.get("steps")
    successful_roles = sorted({
        item["role"]
        for item in attempts
        if isinstance(item, dict)
        and item.get("status") == "success"
        and isinstance(item.get("role"), str)
        and item["role"] in allowed_roles
    })
    return {
        "evidence_kind": evidence_kind,
        "progress_available": True,
        "plan_version": _safe_nonnegative_int(progress.get("plan_version")),
        "review_plan_version": (
            _safe_nonnegative_int(review_source.get("plan_version"))
            if isinstance(review_source, dict)
            else None
        ),
        "review_origin": (
            review_source.get("origin")
            if isinstance(review_source, dict)
            and review_source.get("origin") in allowed_roles
            else None
        ),
        "planned_steps": len(steps) if isinstance(steps, list) else None,
        "reported_steps": (
            sum(isinstance(step, dict) and step.get("reported") is True for step in steps)
            if isinstance(steps, list)
            else None
        ),
        "accepted_steps": (
            sum(
                isinstance(step, dict)
                and step.get("reported") is True
                and step.get("verdict") == "ACCEPT"
                and step.get("valid") is True
                for step in steps
            )
            if isinstance(steps, list)
            else None
        ),
        "successful_roles": successful_roles,
        "tool_calls": (
            _safe_nonnegative_int(budget.get("tool_calls"))
            if isinstance(budget, dict)
            else None
        ),
    }


def _check_process_path(
    sample: dict[str, Any],
    safe_evidence: dict[str, Any],
    task: dict[str, Any],
    transport: dict[str, Any],
) -> dict[str, Any]:
    """Count only a naturally executed and completed planned trace as multistep coverage."""
    if sample.get("type") != "multistep":
        return _check("PASS", "natural_multistep_not_required")
    process = safe_evidence.get("process_path")
    if isinstance(process, dict) and process.get("progress_available") is False:
        attempts = safe_evidence.get("request_attempts")
        roles = {
            item.get("role")
            for item in attempts
            if isinstance(item, dict)
            and item.get("status") in {"success", "error", "unknown"}
            and item.get("dispatch_status") != "not_submitted"
        } if isinstance(attempts, list) else set()
        planning_roles = {"planner", "reasoner", "reason_noncoding", "step_verifier"}
        if (
            task.get("status") == "PASS"
            and transport.get("status") == "PASS"
            and "whole_solution_verifier" in roles
            and not roles.intersection(planning_roles)
        ):
            return _check("NOT_RUN", "natural_multistep_path_not_observed")
        return _check("UNKNOWN", "solver_progress_unavailable")
    if not isinstance(process, dict) or any(
        process.get(key) is None
        for key in (
            "plan_version",
            "planned_steps",
            "reported_steps",
            "accepted_steps",
            "tool_calls",
        )
    ):
        return _check("UNKNOWN", "solver_progress_unavailable")
    version = process["plan_version"]
    planned_steps = process["planned_steps"]
    reported_steps = process["reported_steps"]
    if version == 0 and planned_steps == 0:
        return _check("NOT_RUN", "natural_multistep_path_not_observed")
    if version == 0 or planned_steps == 0:
        return _check("FAIL", "solver_progress_inconsistent")
    if task.get("status") == "FAIL":
        return _check("FAIL", "natural_multistep_delivery_failed")
    if task.get("status") == "UNKNOWN":
        return _check("UNKNOWN", "natural_multistep_delivery_unknown")
    if process.get("review_plan_version") is None or process.get("review_origin") is None:
        return _check("UNKNOWN", "whole_review_source_unavailable")
    if (
        reported_steps != planned_steps
        or process["accepted_steps"] != planned_steps
    ):
        return _check("NOT_RUN", "natural_multistep_trace_incomplete")
    roles = set(process.get("successful_roles", []))
    if not (
        {"planner", "step_verifier", "final_generator"} <= roles
        and roles.intersection({"reasoner", "reason_noncoding"})
    ):
        return _check("NOT_RUN", "natural_multistep_trace_incomplete")
    if process["tool_calls"] > 0:
        return _check("UNKNOWN", "tool_receipt_consumption_unverified")
    if (
        process["review_origin"] != "final_generator"
        or process["review_plan_version"] != version
    ):
        return _check("FAIL", "final_delivery_plan_mismatch")
    if task.get("status") != "PASS":
        return _check("NOT_RUN", "natural_multistep_delivery_unverified")
    if (
        process.get("evidence_kind") != "provider_live"
        or safe_evidence.get("execution_mode") != "live"
    ):
        return _check("NOT_RUN", "provider_live_trace_required")
    if transport.get("status") != "PASS":
        return _check("UNKNOWN", "provider_live_transport_unverified")
    return _check("PASS", "natural_multistep_path_observed")
