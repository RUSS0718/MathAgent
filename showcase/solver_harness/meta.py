"""Tool-free, persistent Meta diagnostics; only the controller commits decisions."""

from copy import deepcopy
from datetime import UTC, datetime

from ..redaction import redact
from .explore import ModelPort, ScriptedModelPort

MetaPort = ModelPort
ScriptedMetaPort = ScriptedModelPort
_DECISION_KEYS = {
    "decision",
    "reason_summary",
    "plan_summary",
    "forbidden_directions",
    "reusable_results",
    "trace_back_to",
}
_GUIDANCE_KEYS = {
    "action_type",
    "specific_task",
    "use_pure_reasoning",
    "trace_back_to",
    "rationale",
}


def _parse(reply, guidance):
    keys = _GUIDANCE_KEYS if guidance else _DECISION_KEYS
    if not isinstance(reply, dict) or set(reply) != keys:
        raise ValueError("invalid_meta_schema")
    texts = ("specific_task", "rationale") if guidance else ("reason_summary", "plan_summary")
    if any(not isinstance(reply[k], str) for k in texts):
        raise ValueError("invalid_meta_text")
    if not reply[texts[0]].strip():
        raise ValueError("missing_specific_task" if guidance else "missing_reason_summary")
    target = reply["trace_back_to"]
    if target is not None and (
        isinstance(target, bool) or not isinstance(target, int) or target < 1
    ):
        raise ValueError("invalid_trace_back_target")
    if guidance:
        if (
            reply["action_type"]
            not in {"explore_more", "retry_different_method", "trace_back", "replan"}
            or type(reply["use_pure_reasoning"]) is not bool
        ):
            raise ValueError("invalid_meta_guidance")
        trace = reply["action_type"] == "trace_back"
    else:
        if reply["decision"] not in {"CONTINUE", "TRACE_BACK", "APPROVE_REPLAN", "ABORT"}:
            raise ValueError("invalid_meta_decision")
        for key in ("forbidden_directions", "reusable_results"):
            if not isinstance(reply[key], list) or any(not isinstance(x, str) for x in reply[key]):
                raise ValueError("invalid_meta_list")
        trace = reply["decision"] == "TRACE_BACK"
    if trace != (target is not None):
        raise ValueError("invalid_trace_back_target")
    return redact(deepcopy(reply))


def run_meta(harness, run, *, meta_port, metadata, max_model_calls, max_runtime_seconds):
    """Route a strict response, retaining only safe summaries in the run session."""
    if meta_port is None or run["state"]["phase"] == "TERMINAL":
        return run
    state = run["state"]
    guidance = metadata.get("meta_guidance")
    trigger = metadata.get("meta_trigger")
    if guidance is None and trigger is None and state["phase"] != "META_DECIDE":
        return run
    if guidance is not None:
        if not isinstance(guidance, dict) or guidance.get("failure_type") not in {
            "timeout",
            "code_issue",
            "stuck",
        }:
            raise ValueError("invalid_meta_failure_type")
    elapsed = (datetime.now(UTC) - datetime.fromisoformat(state["created_at"])).total_seconds()
    if state["counters"]["model_calls"] >= max_model_calls or elapsed >= max_runtime_seconds:
        reason = (
            "runtime_budget_exhausted"
            if elapsed >= max_runtime_seconds
            else "model_call_budget_exhausted"
        )
        return harness.commit_event(
            run["run_id"],
            expected_revision=run["state_revision"],
            event={
                "event_id": f"meta-budget-{run['state_revision']}",
                "type": "budget_exhausted",
                "reason": reason,
            },
            state_updates={
                "phase": "TERMINAL",
                "status": "partial_budget_exhausted",
                "budget": {**state.get("budget", {}), "exhaustion_reason": reason},
                "final_response": "Budget exhausted before Meta diagnosis; no further intervention was dispatched.",
            },
        )
    history = deepcopy(state.get("meta_history", []))
    session = f"meta:{run['run_id']}"
    request = {
        "role": "meta",
        "run_id": run["run_id"],
        "session_key": session,
        "allowed_tools": [],
        "tool_policy": {"allow": []},
        "trigger": str(trigger or ("failure" if guidance else "plan-blocked")),
        "guidance_request": redact(deepcopy(guidance)),
        "history": history,
        "plan_version": state["plan_version"],
        "progress": {"current_step": state["current_step"], "phase": state["phase"]},
        "failures": redact(deepcopy(state["failure_records"])),
        "budget": {"max_model_calls": max_model_calls, **state["counters"]},
    }
    revision = run["state_revision"]
    run = harness.commit_event(
        run["run_id"],
        expected_revision=revision,
        event={"event_id": f"meta-dispatched-{revision}", "type": "meta_dispatched"},
        state_updates={
            "counters": {**state["counters"], "model_calls": state["counters"]["model_calls"] + 1}
        },
    )
    request["call_id"] = f"{session}:{revision}"
    request["state_revision"] = run["state_revision"]
    request = harness.prepare_request(run, request)
    request.update(allowed_tools=[], tool_policy={"allow": []})
    try:
        decision = _parse(dict(meta_port.complete(deepcopy(request))), guidance is not None)
        target = decision["trace_back_to"]
        if target is not None:
            steps = state.get("plan", {}).get("steps", [])
            current_index = next(
                (i for i, step in enumerate(steps, 1) if step["step_id"] == state["current_step"]),
                0,
            )
            if target > current_index:
                raise ValueError("invalid_trace_back_target")
    except Exception:
        return harness.commit_event(
            run["run_id"],
            expected_revision=run["state_revision"],
            event={
                "event_id": f"meta-invalid-{revision}",
                "type": "meta_invalid",
                "reason": "invalid_or_failed_response",
            },
        )
    history.extend(
        [
            {"role": "user", "summary": request["trigger"], "plan_version": state["plan_version"]},
            {"role": "assistant", "decision": decision},
        ]
    )
    action = decision.get("decision", decision.get("action_type"))
    phase = {
        "CONTINUE": "STEP_EXECUTE",
        "TRACE_BACK": "TRACE_BACK",
        "APPROVE_REPLAN": "REPLAN",
        "ABORT": "TERMINAL",
        "trace_back": "TRACE_BACK",
        "replan": "META_DECIDE",
        "explore_more": "EXPLORE",
        "retry_different_method": "STEP_EXECUTE",
    }[action]
    updates = {
        "phase": phase,
        "meta_history": history,
        "meta_decision": decision,
        "session_refs": {**state["session_refs"], "meta": session},
        "meta_interventions": [*state["meta_interventions"], {"session_key": session, **decision}],
    }
    if action == "ABORT":
        updates.update(
            status="partial_aborted", final_response="Run aborted: " + decision["reason_summary"]
        )
    if decision.get("use_pure_reasoning"):
        updates.update(tool_policy={"allow": []}, reasoning_mode="reason_noncoding")
    if target is not None:
        updates["trace_back_to"] = target
    return harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={
            "event_id": f"meta-decided-{revision}",
            "type": "meta_decided",
            "decision": decision,
        },
        state_updates=updates,
    )
