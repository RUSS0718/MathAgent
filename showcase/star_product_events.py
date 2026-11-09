"""Categorical Solver decisions for the public timeline; no model reports."""

import hashlib
import hmac
import re
from collections.abc import Mapping

from .redaction import redact
from .run_budget import public_solver_call_id
from .solver_harness.skills import PROTOCOLS

_PUBLIC_CALL_ROLES = frozenset({
    "reasoner", "reason_noncoding", "explore", "explore_polish", "planner", "researcher",
    "step_verifier", "final_generator", "whole_solution_verifier", "meta", "meta_strategist",
})
_FAILED_CALL_STATUSES = frozenset({
    "tool_error", "protocol_failed", "policy_rejected", "budget_rejected",
    "ignored_late_response",
})
_FAILED_RECEIPT_STATUSES = frozenset({
    "not_executed", "output_limit", "canceled", "unavailable", "timeout", "tool_error", "network_error",
    "parse_error", "unknown_outcome", "rejected",
})


def public_solver_event_id(run, event):
    """Return a stable per-Run event ID without exposing its internal event key."""
    run_id = str(run["run_id"])
    salt = str(run["state"].get("run_salt") or run_id).encode("utf-8")
    message = f"{run_id}:{event.get('event_id', '')}".encode()
    digest = hmac.new(salt, message, hashlib.sha256).hexdigest()[:32]
    return f"solver_event_{digest}"


def decision_fields(event, state, invocations=()):
    fields = {key: event[key] for key in (
        "assessment", "round", "next_phase", "goal_gate", "logic_gate",
        "verdict", "valid", "trace_back_to", "from_step_index", "attempt_index",
        "archived_plan_version", "archived_step_count", "invalidated_result_count",
        "rescued_result_count", "failure_type", "action_type", "use_pure_reasoning",
        "specific_task_consumed", "triggered_by", "counterexample_verdict",
        "decision_revision", "classified_outcomes", "rejected_outcomes",
        "stream_metrics", "stream_activity", "checkpoint_status", "checkpoint_round",
        "transport", "transport_reason", "transport_selection_reason",
        "transport_evidence_kind", "transport_profile_fingerprint",
        "transport_profile_set_fingerprint",
        "transport_policy", "new_run_required",
        "route_id", "parent_route_id", "route_kind", "frontier_digest",
        "route_status", "route_reason", "policy_version", "pareto_route_ids",
        "selected_route_id", "route_count", "route_replayable",
    ) if key in event}
    run_id = state.get("run_id")
    if isinstance(run_id, str) and run_id:
        fields["run_id"] = run_id
    roles = {
        "step_reported": "reasoner",
        "challenge_dispatched": "reasoner",
        "challenge_replied": "reasoner",
        "step_reviewed": "step_verifier",
        "explore_assessed": "explore",
        "exploration_polished": "explore",
        "initial_plan_generated": "planner",
        "plan_replaced": "planner",
        "planner_checkpoint_yielded": "planner",
        "final_candidate_generated": "final_generator",
        "final_candidate_reviewed": "whole_solution_verifier",
        "solution_review_assessed": "whole_solution_verifier",
        "meta_dispatched": "meta",
        "meta_decided": "meta",
        "meta_guidance_decided": "meta",
        "meta_guidance_applied": "reasoner",
        "meta_invalid": "meta",
        "challenge_stalemate": "controller",
        "challenge_escalation_stopped": "controller",
        "route_created": "controller",
        "route_transition": "controller",
        "route_rated": "controller",
        "aprs_decided": "controller",
        "route_rejected": "controller",
    }
    role = event.get("role") or roles.get(event["type"])
    if role in {"reasoner", "reason_noncoding", "explore", "planner", "researcher",
                "step_verifier", "final_generator", "whole_solution_verifier", "meta", "controller"}:
        fields["role"] = role
    upgrade_reason = event.get("upgrade_reason")
    if upgrade_reason in {"round_limit_reached", "meta_escalation_limit_reached"}:
        fields["upgrade_reason"] = upgrade_reason
    if event["type"] == "protocol_failure_unrepaired" and isinstance(event.get("error_category"), str):
        fields["error_category"] = event["error_category"]
    if event["type"] == "step_reviewed" and event.get("verdict") == "CHALLENGE":
        objection = event.get("objection")
        if isinstance(objection, str) and objection.strip():
            fields["objection_summary"] = re.sub(r"\s+", " ", redact(objection).strip())[:500]
    step_id = event.get("step_id")
    plan = state.get("plan")
    if isinstance(step_id, str) and isinstance(plan, dict):
        for number, step in enumerate(plan.get("steps", []), start=1):
            if isinstance(step, dict) and step.get("step_id") == step_id:
                fields["step_id"] = f"步骤 {number}"
                break
    for identity_field in ("plan_version", "attempt_index"):
        identity_value = state.get(identity_field)
        if type(identity_value) is int and identity_value >= 0:
            fields[identity_field] = identity_value
    if state.get("population_policy", {}).get("enabled") is True:
        for key in ("route_id", "parent_route_id", "frontier_digest", "selected_route_id",
                    "pareto_route_ids", "route_count", "route_status", "route_reason"):
            fields.pop(key, None)
        from .solver_harness.population_projection import population_projection

        fields["population"] = population_projection(state)
    if isinstance(event.get("decision"), dict):
        fields["decision"] = event["decision"].get("decision")
    if event["type"] == "hint_prepared":
        fields["hint_source"] = {"none": "none", "user_hint": "user", "meta_auto": "meta"}.get(state.get("hint_mode"), "none")
    if event["type"] == "call_audit":
        fields.pop("plan_version", None)
        fields.pop("attempt_index", None)
        call_id = event.get("call_id")
        calls = state.get("calls", {})
        call = calls.get(call_id) if isinstance(call_id, str) and isinstance(calls, Mapping) else None
        if (
            isinstance(call, Mapping)
            and isinstance(run_id, str)
            and call.get("run_id") == run_id
        ):
            raw_status = call.get("status")
            call_status = (
                "completed" if raw_status == "completed"
                else "failed" if isinstance(raw_status, str) and raw_status in _FAILED_CALL_STATUSES
                else "unknown"
            )
            receipts = state.get("tool_receipts", [])
            receipts = receipts if isinstance(receipts, list) else []
            public_receipts = {
                receipt.get("receipt_id"): receipt
                for receipt in receipts
                if isinstance(receipt, Mapping)
                and isinstance(receipt.get("receipt_id"), str)
                and receipt.get("run_id", run_id) == run_id
            }
            consumed_receipt_ids = []
            consumed_ids = call.get("consumed_receipt_ids", [])
            if isinstance(consumed_ids, list):
                for receipt_id in consumed_ids:
                    receipt = public_receipts.get(receipt_id)
                    if receipt is not None:
                        consumed_receipt_ids.append(public_solver_event_id(
                            {"run_id": run_id, "state": state},
                            {"event_id": receipt["receipt_id"]},
                        ))
            call_fields = {
                "solver_call_id": public_solver_call_id(run_id, call_id),
                "run_id": run_id,
                "call_status": call_status,
                "consumed_receipt_ids": consumed_receipt_ids,
            }
            for identity_field in ("plan_version", "attempt_index"):
                identity_value = call.get(identity_field)
                if type(identity_value) is int and identity_value >= 0:
                    call_fields[identity_field] = identity_value
            role = call.get("role")
            if isinstance(role, str) and role in _PUBLIC_CALL_ROLES:
                call_fields["role"] = role
            fields.update(call_fields)
    if event["type"] == "tool_receipt" and isinstance(event.get("receipt"), Mapping):
        fields.pop("plan_version", None)
        fields.pop("attempt_index", None)
        receipt = event["receipt"]
        receipt_run_id = receipt.get("run_id", run_id)
        receipt_id = receipt.get("receipt_id")
        if (
            isinstance(run_id, str)
            and receipt_run_id == run_id
            and isinstance(receipt_id, str)
            and receipt_id
            and event.get("event_id") == receipt_id
        ):
            raw_status = receipt.get("status")
            receipt_status = (
                "success" if raw_status == "success" and receipt.get("executed") is True
                else "failed" if isinstance(raw_status, str) and raw_status in _FAILED_RECEIPT_STATUSES
                else "unknown"
            )
            receipt_fields = {
                "receipt_id": public_solver_event_id({"run_id": run_id, "state": state}, event),
                "run_id": run_id,
                "receipt_status": receipt_status,
            }
            executed = receipt.get("executed")
            if type(executed) is bool:
                receipt_fields["receipt_executed"] = executed
            for identity_field in ("plan_version", "attempt_index"):
                identity_value = receipt.get(identity_field)
                if type(identity_value) is int and identity_value >= 0:
                    receipt_fields[identity_field] = identity_value
            fields.update(receipt_fields)
    if event["type"] in {
        "challenge_replied", "step_reviewed", "meta_decided",
        "meta_guidance_decided", "meta_guidance_applied", "trace_back_applied",
    } and role in {
        "reasoner", "step_verifier", "meta"
    }:
        invocation = next(
            (item for item in reversed(invocations) if item.get("role") == role), None
        )
        usage = invocation.get("usage") if isinstance(invocation, dict) else None
        if isinstance(usage, dict):
            fields["usage"] = {
                key: value if type(value) is int and value >= 0 else None
                for key, value in usage.items()
                if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
            }
    invocation_roles = {
        "reasoner": {"reasoner", "reason_noncoding"},
        "step_verifier": {"step_verifier"},
        "whole_solution_verifier": {"whole_solution_verifier"},
        "final_generator": {"final_generator"},
        "explore": {"explore", "explore_polish"},
        "meta": {"meta", "meta_strategist"},
        "planner": {"planner"},
        "researcher": {"researcher"},
    }
    accepted_roles = invocation_roles.get(role, {role}) if role else set()
    invocation = next(
        (item for item in reversed(invocations) if item.get("role") in accepted_roles), None
    ) if role else None
    if isinstance(invocation, dict):
        stream = invocation.get("stream")
        # Streaming evidence publishes only fragment/byte counts and status.
        if (
            isinstance(stream, Mapping)
            and type(stream.get("fragments")) is int
            and stream["fragments"] >= 0
            and type(stream.get("bytes")) is int
            and stream["bytes"] >= 0
            and isinstance(stream.get("status"), str)
        ):
            fields["stream_metrics"] = {
                "fragments": stream["fragments"],
                "bytes": stream["bytes"],
                "status": stream["status"],
            }
        calls = state.get("calls", {})
        if isinstance(calls, Mapping):
            call = next(
                (item for item in reversed(list(calls.values()))
                 if isinstance(item, Mapping) and item.get("role") in accepted_roles),
                None,
            )
            activity = call.get("stream_metrics") if isinstance(call, Mapping) else None
            activity = activity if isinstance(activity, Mapping) else {}
            fields["stream_activity"] = {
                key: (activity.get(key) if activity.get(key) is not None else "unavailable")
                for key in (
                    "dispatched_at", "response_headers_at", "first_event_at",
                    "first_reasoning_at", "first_content_at", "last_content_at",
                    "last_activity_at",
                    "completion_at", "event_count", "reasoning_chars", "content_bytes",
                    "usage_known", "status",
                )
            }
        skills = invocation.get("active_skill_ids")
        if isinstance(skills, list) and all(isinstance(item, str) for item in skills):
            fields["active_skill_ids"] = skills
            fields["skill_protocol_version"] = "1"
            fields["skill_protocols"] = [
                {
                    "id": key,
                    "version": "1",
                    "trigger": PROTOCOLS[key]["trigger"],
                    "permissions": list(PROTOCOLS[key]["permissions"]),
                }
                for key in skills
                if key in PROTOCOLS
            ]
        fingerprint = invocation.get("prompt_fingerprint")
        if isinstance(fingerprint, str) and re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            fields["prompt_fingerprint"] = fingerprint
        for key in ("prompt_layers_fingerprint", "schema_fingerprint", "input_fingerprint"):
            fingerprint = invocation.get(key)
            if isinstance(fingerprint, str) and re.fullmatch(r"[0-9a-f]{64}", fingerprint):
                fields[key] = fingerprint
    return fields
