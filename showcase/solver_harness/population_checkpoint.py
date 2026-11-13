"""Validate route-local checkpoint progress without promoting mathematical evidence."""

from .reasoner_checkpoint import current_checkpoints
from .verification import normalize_verdict


def continuation_audit(branch, events, route, action):
    """Bind an accepted YIELD to this action's completed Reasoner and Verifier."""
    step_id = branch.get("current_step")
    step = branch.get("steps", {}).get(step_id, {})
    checkpoints = current_checkpoints(branch)
    if (branch.get("phase") != "STEP_EXECUTE" or branch.get("status") != "running"
            or step.get("status") != "CHECKPOINT_ACCEPTED" or not checkpoints):
        return None
    checkpoint = checkpoints[-1]
    if (checkpoint.get("status") != "YIELD" or not checkpoint.get("gaps")
            or checkpoint.get("checkpoint_id") != step.get("checkpoint_id")):
        return None
    report_id = checkpoint.get("call_id")
    report = branch.get("calls", {}).get(report_id, {})
    if (report.get("response", {}).get("checkpoint", {}).get("checkpoint_id")
            != checkpoint["checkpoint_id"]):
        return None
    event = next((event for event in reversed(events)
                  if event.get("type") == "step_reviewed"
                  and event.get("step_id") == step_id
                  and event.get("checkpoint_id") == checkpoint["checkpoint_id"]
                  and event.get("verdict") == "ACCEPT"), None)
    if event is None:
        return None
    for review_id, review in branch.get("calls", {}).items():
        if (review.get("role") != "step_verifier"
                or review.get("request", {}).get("checkpoint", {}).get("checkpoint_id")
                != checkpoint["checkpoint_id"]):
            continue
        verdict = normalize_verdict(review.get("response"), 1)
        if not verdict["valid"] or verdict["verdict"] != "ACCEPT":
            continue
        if any(call.get("status") != "completed"
               or call.get("route_id") != route["route_id"]
               or call.get("action_id") != action["action_id"]
               or call.get("plan_version") != branch.get("plan_version")
               or call.get("attempt_index") != branch.get("attempt_index")
               for call in (report, review)):
            continue
        if report.get("role") != "reasoner":
            continue
        return {"accepted": True, "reason": None, "type": "population_checkpoint_accepted",
                "source_event_ids": [event["event_id"]], "report_call_ids": [report_id],
                "review_call_ids": [review_id], "merged_result_ids": [],
                "merged_obligation_ids": []}
    return None
