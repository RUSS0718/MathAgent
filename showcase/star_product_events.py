"""Categorical Solver decisions for the public timeline; no model reports."""

import hashlib
import hmac


def public_solver_event_id(run, event):
    """Return a stable per-Run event ID without exposing its internal event key."""
    run_id = str(run["run_id"])
    salt = str(run["state"].get("run_salt") or run_id).encode("utf-8")
    message = f"{run_id}:{event.get('event_id', '')}".encode()
    digest = hmac.new(salt, message, hashlib.sha256).hexdigest()[:32]
    return f"solver_event_{digest}"


def decision_fields(event, state):
    fields = {key: event[key] for key in (
        "assessment", "round", "next_phase", "goal_gate", "logic_gate",
        "verdict", "valid", "trace_back_to",
    ) if key in event}
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
    return fields
