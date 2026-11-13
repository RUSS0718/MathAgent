"""Versioned admission identity and read-only state for ordinary Faithful Jobs."""


def task_identity(pipeline, mode):
    """Freeze the enabled feature upper bound; it is not execution evidence."""
    preset = getattr(pipeline, "preset_config", None)
    config = preset(mode) if callable(preset) else {}
    features = config.get("features", {})
    if features.get("auto_problem_spec") is not True:
        return {}
    return {"faithful": {
        "version": "faithful-task-v1", "input_version": 1,
        "capability_snapshot": {
            "version": "faithful-capabilities-v1", "solver_mode": mode,
            "maturity": "experimental",
            "features": {key: value is True for key, value in features.items()},
        },
    }}


def _public_question(question, *, include_answer=True):
    from .redaction import redact

    fields = ("request_id", "task_id", "input_version", "question", "reason", "status")
    if include_answer:
        fields += ("answer",)
    return redact({key: question[key] for key in fields if key in question})


def public_run_result(result):
    """Do not copy internal clarification persistence into a Run snapshot."""
    public = dict(result)
    identity = public.get("faithful")
    if isinstance(identity, dict) and (reply := identity.get("clarification_reply")):
        public["faithful"] = {key: value for key, value in identity.items() if key != "clarification_reply"}
        public["faithful"]["clarification"] = _public_question(reply, include_answer=False)
    return public


def attach_task_state(payload, *, allowed_actions=None, question=None):
    """Project committed Job/Solver state without creating another controller."""
    result = payload.get("result") or {}
    identity = result.get("faithful")
    if not isinstance(identity, dict):
        return payload
    solver = result.get("solver") or {}
    status = payload["status"]
    reason = solver.get("budget_exhaustion_reason") or solver.get("result_reason") or payload.get("error")
    recovery = solver.get("recovery") or {}
    if status == "succeeded":
        phase = "completed"
    elif status == "canceled":
        phase = "canceled"
    elif status == "waiting_input":
        phase = "waiting_input"
    elif status == "failed":
        phase = ("unknown" if recovery.get("unknown_calls") or recovery.get("unknown_tools")
                 else "budget_exhausted" if solver.get("status") == "partial_budget_exhausted"
                 else "protocol_error" if "protocol" in str(reason) else "failed")
    else:
        phase = "intake" if solver.get("intake_status") == "pending" else solver.get("phase", status).lower()
    result["faithful"] = {
        **identity, "specification_version": solver.get("specification_version"),
        "state_revision": solver.get("state_revision", 0),
        "phase": phase, "reason": reason,
        "allowed_actions": (allowed_actions if allowed_actions is not None else
                            ["cancel"] if status in {"queued", "running", "waiting_input"} else []),
    }
    question = identity.get("clarification_reply") or question
    if question:
        result["faithful"].pop("clarification_reply", None)
        result["faithful"]["clarification"] = _public_question(question)
        result["faithful"]["input_version"] = question["input_version"] + int(question["status"] == "answered")
    payload["result"] = result
    return payload
