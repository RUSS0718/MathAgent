"""Categorical Solver decisions for the public timeline; no model reports."""

import hashlib
import hmac
import re

from .redaction import redact
from .solver_harness.skills import PROTOCOLS


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
    ) if key in event}
    roles = {
        "step_reported": "reasoner",
        "challenge_dispatched": "reasoner",
        "challenge_replied": "reasoner",
        "step_reviewed": "step_verifier",
        "meta_dispatched": "meta",
        "meta_decided": "meta",
        "meta_guidance_decided": "meta",
        "meta_guidance_applied": "reasoner",
        "meta_invalid": "meta",
        "challenge_stalemate": "controller",
        "challenge_escalation_stopped": "controller",
    }
    role = event.get("role") or roles.get(event["type"])
    if role in {"reasoner", "reason_noncoding", "explore", "planner", "researcher",
                "step_verifier", "whole_solution_verifier", "meta", "controller"}:
        fields["role"] = role
    upgrade_reason = event.get("upgrade_reason")
    if upgrade_reason in {"round_limit_reached", "meta_escalation_limit_reached"}:
        fields["upgrade_reason"] = upgrade_reason
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
    if state.get("plan_version"):
        fields["plan_version"] = state["plan_version"]
    if isinstance(event.get("decision"), dict):
        fields["decision"] = event["decision"].get("decision")
    if event["type"] == "hint_prepared":
        fields["hint_source"] = {"none": "none", "user_hint": "user", "meta_auto": "meta"}.get(state.get("hint_mode"), "none")
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
    return fields
