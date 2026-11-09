"""Read-only AC23 projection of model, computation, and Lean attempts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .run_budget import public_solver_call_id
from .star_product_events import public_solver_event_id

_MODEL_ROLES = frozenset({
    "explore", "explore_polish", "reasoner", "reason_noncoding",
    "whole_solution_verifier",
})
_FAILED_CALLS = frozenset({"provider_failed", "invalid_response", "policy_rejected"})
_FAILED_TOOLS = frozenset({
    "not_executed", "output_limit", "canceled", "unavailable", "tool_error",
    "network_error", "parse_error", "rejected",
})
_SAFE_REASONS = frozenset({
    "artifact_integrity_failed", "execution_outcome_unknown", "formal_backend_unavailable",
    "formal_dependency_audit_incomplete", "formal_environment_drift",
    "formal_environment_identity_unavailable", "formal_output_limit", "formal_target_unsupported",
    "invalid_response", "live_not_enabled", "network_error", "output_limit_exceeded",
    "provider_failed", "run_deadline_exhausted", "run_model_budget_exhausted",
    "run_tool_budget_exhausted", "tool_arguments_not_serializable",
    "tool_arguments_must_be_object", "tool_budget_exhausted", "tool_execution_error",
    "tool_input_too_large", "tool_not_allowed", "tool_not_permitted_for_profile",
    "tool_not_registered", "tool_schema_invalid", "tool_timeout", "unavailable",
})


def _safe_reason(value: Any) -> str | None:
    return value if isinstance(value, str) and value in _SAFE_REASONS else None


def prover_route_projection(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Project existing persisted attempts without dispatching or accepting new work."""
    run_id = state.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        return []
    result = []
    calls = state.get("calls")
    if isinstance(calls, Mapping):
        for call_id, call in calls.items():
            if not isinstance(call_id, str) or not isinstance(call, Mapping):
                continue
            role = call.get("role")
            if role not in _MODEL_ROLES or call.get("run_id") != run_id:
                continue
            raw_status = call.get("status")
            status = ("completed" if raw_status == "completed" else
                      "failed" if raw_status in _FAILED_CALLS else "unknown")
            usage = call.get("usage") if isinstance(call.get("usage"), Mapping) else {}
            cost_fields = ("prompt_tokens", "completion_tokens", "total_tokens")
            if "usage" in call and call["usage"] is None:
                cost = dict.fromkeys(cost_fields)
            else:
                cost = {key: usage[key] for key in cost_fields if key in usage}
            response = call.get("response") if isinstance(call.get("response"), Mapping) else {}
            grade = None
            if (role == "whole_solution_verifier" and status == "completed"
                    and response.get("verdict") == "ACCEPT"
                    and state.get("status") == "completed_llm_reviewed"):
                grade = "LLM_REVIEWED"
            result.append({
                "backend_id": "llm_prover",
                "target_type": ("natural_language_review" if role == "whole_solution_verifier"
                                 else "natural_language_draft"),
                "selection_reason": f"solver_role:{role}",
                "environment_identity": {
                    key: call[key] for key in ("requested_model", "effective_model", "returned_model")
                    if isinstance(call.get(key), str) and call[key]
                },
                "input_format": "intern-role-json-schema-v1",
                "output_format": "intern-role-json-v1",
                "deterministic": False,
                "unavailable_reason": (_safe_reason(call.get("error_category"))
                                       if status != "completed" else None),
                "attempt_id": public_solver_call_id(run_id, call_id),
                "parent_attempt_id": call.get("retry_of"),
                "role": role,
                "status": status,
                "grade": grade,
                "maximum_grade": "LLM_REVIEWED",
                "cost": cost,
                "lineage": {"attempt_id": public_solver_call_id(run_id, call_id),
                            "parent_attempt_id": call.get("retry_of")},
            })

    receipts = state.get("tool_receipts")
    if isinstance(receipts, list):
        previous_receipts = {}
        receipt_sequences = {}
        seen_receipts = set()
        for receipt in receipts:
            if not isinstance(receipt, Mapping) or receipt.get("run_id", run_id) != run_id:
                continue
            tool = receipt.get("tool")
            if tool not in {"polynomial_check", "python_math"}:
                continue
            receipt_id = receipt.get("receipt_id")
            if not isinstance(receipt_id, str) or not receipt_id:
                continue
            public_id = public_solver_event_id(
                {"run_id": run_id, "state": state}, {"event_id": receipt_id})
            if public_id in seen_receipts:
                continue
            seen_receipts.add(public_id)
            receipt_scope = (receipt.get("step_id"), receipt.get("claim_index"), tool)
            parent_attempt_id = previous_receipts.get(receipt_scope)
            previous_receipts[receipt_scope] = public_id
            sequence = receipt_sequences.get(receipt_scope, 0) + 1
            receipt_sequences[receipt_scope] = sequence
            raw_status = receipt.get("status")
            status = ("completed" if raw_status == "success" and receipt.get("executed") is True
                      and receipt.get("unknown_outcome") is not True else
                      "timeout" if raw_status == "timeout" else
                      "unknown" if raw_status == "unknown_outcome"
                      or receipt.get("unknown_outcome") is True else
                      raw_status if raw_status in {"unavailable", "not_executed"}
                      else "failed" if raw_status in _FAILED_TOOLS else "unknown")
            grade = None
            output = receipt.get("output")
            if status == "completed" and receipt.get("output_available") is True:
                if (tool == "polynomial_check" and isinstance(output, Mapping)
                        and output.get("candidate_status") == "pass"):
                    grade = "L1"
                elif receipt.get("comparison_status") == "matched":
                    grade = "L1"
            result.append({
                "backend_id": "math_tool_backend",
                "target_type": "computable",
                "selection_reason": "explicit_registered_tool_request",
                "environment_identity": {
                    key: receipt[key] for key in ("source", "sandbox_policy_version", "image")
                    if isinstance(receipt.get(key), str) and receipt[key]
                },
                "input_format": "registered-tool-schema-v1",
                "output_format": "tool-receipt-v1",
                "deterministic": tool == "polynomial_check",
                "unavailable_reason": (_safe_reason(receipt.get("reason"))
                                       if status != "solved" else None),
                "attempt_id": public_id,
                "parent_attempt_id": parent_attempt_id,
                "tool": tool,
                "status": status,
                "unknown_outcome": receipt.get("unknown_outcome") is True,
                "grade": grade,
                "maximum_grade": "L1",
                "cost": {key: receipt[key] for key in (
                    "duration_seconds", "observed_output_bytes") if key in receipt},
                "lineage": {"attempt_id": public_id,
                    "parent_attempt_id": parent_attempt_id,
                    "sequence": sequence},
            })

    formal = state.get("formal_verification")
    if isinstance(formal, Mapping):
        attempts = formal.get("attempts")
        if isinstance(attempts, list):
            for attempt in attempts:
                if not isinstance(attempt, Mapping):
                    continue
                backend = attempt.get("backend")
                if not isinstance(backend, str) or not backend:
                    continue
                grade = attempt.get("grade") if attempt.get("grade") in {"L2", "L3"} else None
                attempt_id = attempt.get("attempt_id")
                result.append({
                    "backend_id": backend,
                    "target_type": "stable_lean_goal",
                    "attempt_id": attempt_id,
                    "parent_attempt_id": attempt.get("parent_attempt_id"),
                    "status": attempt.get("status", "unknown"),
                    "grade": grade,
                    "maximum_grade": attempt.get("maximum_grade") or grade or "L2",
                    "selection_reason": attempt.get("selection_reason") or "explicit_formal_policy",
                    "environment_identity": dict(attempt.get("environment_identity") or {}),
                    "input_format": attempt.get("input_format"),
                    "output_format": attempt.get("output_format"),
                    "deterministic": attempt.get("deterministic"),
                    "unavailable_reason": attempt.get("unavailable_reason"),
                    "cost": dict(attempt.get("cost") or {}),
                    "lineage": dict(attempt.get("lineage") or {}),
                })
    return result


__all__ = ["prover_route_projection"]
