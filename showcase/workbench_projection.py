"""Versioned, categorical collaboration facts; never publish model report bodies."""

import hashlib
import hmac


def collaboration_fields(event, state):
    """Bind messages to a run/plan/attempt/step and expose known changes only."""
    kind = event["type"]
    routes = {
        "challenge_replied": ("reasoner", "step_verifier", "reply", "已提交本步异议回复"),
        "challenge_stalemate": ("step_verifier", "meta", "escalation", "质询达到上限，升级裁决"),
        "meta_decided": ("meta", "controller", "decision", "Meta 裁决已记录"),
        "trace_back_applied": ("controller", "reasoner", "rollback", "回退已应用，重算尚未完成"),
    }
    if kind == "step_reviewed" and event.get("verdict") == "CHALLENGE":
        route = ("step_verifier", "reasoner", "challenge", "本步收到质疑")
    else:
        route = routes.get(kind)
    if route is None:
        return None
    run = str(state.get("run_id", ""))
    salt = str(state.get("run_salt") or run).encode()

    def identity(value):
        return hmac.new(salt, f"{run}:{value}".encode(), hashlib.sha256).hexdigest()[:32]

    failure = next((item for item in reversed(state.get("failure_records", []))
                    if item.get("kind") == "trace_back"
                    and item.get("attempt_index") == max(0, state.get("attempt_index", 0) - 1)), {})
    step_id = (failure.get("from_step") if kind == "trace_back_applied" else None) or event.get("step_id") or state.get("current_step")
    steps = (state.get("plan") or {}).get("steps", [])
    label = next((f"步骤 {i}" for i, step in enumerate(steps, 1)
                  if step.get("step_id") == step_id), None)
    attempt = state.get("attempt_index", 0)
    # Rollback commits advance the attempt: the ruling belongs to its old thread.
    thread_attempt = max(0, attempt - 1) if kind == "trace_back_applied" else attempt
    decision = event.get("decision")
    if (kind == "meta_decided" and isinstance(decision, dict)
            and decision.get("decision") == "CONTINUE" and "attempt_index" in event):
        thread_attempt = max(0, attempt - 1)
    version = state.get("plan_version", 0)
    result = {
        "version": "workbench-v1",
        "thread_id": "thread_" + identity(f"thread:{version}:{thread_attempt}:{step_id}"),
        "message_id": "message_" + identity(str(event.get("event_id", ""))),
        "from_role": route[0], "to_role": route[1], "kind": route[2],
        "summary": route[3], "content_status": "not_published",
        "thread_status": "decided" if kind in {"meta_decided", "trace_back_applied"} else "open",
        "plan_version": version, "attempt_index": thread_attempt,
    }
    if label:
        result["step_label"] = label
    if kind == "meta_decided":
        decision = event.get("decision")
        chosen = decision.get("decision") if isinstance(decision, dict) else decision
        if chosen in {"CONTINUE", "TRACE_BACK", "APPROVE_REPLAN", "ABORT"}:
            result["chosen"] = chosen
        # Options and reasoning are not publicly approved evidence.
    if kind == "trace_back_applied":
        archived = failure.get("archived_steps", {})
        result["changes"] = [
            {"op": "del", "step_label": f"步骤 {i}", "summary": "旧步骤状态已撤销"}
            for i, step in enumerate(steps, 1) if step.get("step_id") in archived
        ]
        result["previous_attempt_index"] = thread_attempt
        result["next_attempt_index"] = attempt
        result["next_state_revision"] = state.get("state_revision", 0)
    return result
