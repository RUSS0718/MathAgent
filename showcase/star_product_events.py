"""Categorical Solver decisions for the public timeline; no model reports."""


def decision_fields(event, state):
    fields = {key: event[key] for key in (
        "assessment", "round", "next_phase", "goal_gate", "logic_gate",
        "verdict", "valid", "trace_back_to",
    ) if key in event}
    if event.get("step_id"):
        fields["step_id"] = event["step_id"]
    if state.get("plan_version"):
        fields["plan_version"] = state["plan_version"]
    if isinstance(event.get("decision"), dict):
        fields["decision"] = event["decision"].get("decision")
    if event["type"] == "hint_prepared":
        fields["hint_source"] = {"none": "none", "user_hint": "user", "meta_auto": "meta"}.get(state.get("hint_mode"), "none")
    return fields
