"""Bind graph evidence to the immutable checkpoint actually reviewed."""

from collections.abc import Mapping


def reviewed_checkpoint_report(state, record, review):
    """Return the original report only for an audited, matching checkpoint review."""
    from .proof_graph_sources import reasoner_report_call, recorded_call
    from .reasoner_checkpoint import parse
    from .verification import normalize_verdict

    request = review["request"]
    checkpoint, report = request.get("checkpoint"), request.get("report")
    if not isinstance(checkpoint, Mapping) or not isinstance(report, Mapping):
        return None
    if (checkpoint not in state.get("reasoner_checkpoints", [])
            or checkpoint.get("run_id") != state.get("run_id")
            or checkpoint.get("step_id") != record.get("source")
            or checkpoint.get("plan_version") != record.get("plan_version")
            or checkpoint.get("attempt_index") != record.get("attempt_index")):
        return None
    call = recorded_call(state, checkpoint.get("call_id"), "reasoner")
    if call is None or call.get("status") != "completed":
        return None
    try:
        payload = parse(call.get("response"))
    except ValueError:
        return None
    if any(checkpoint.get(key) != value for key, value in payload.items()):
        return None
    verification = normalize_verdict(review["response"], request.get("current_step_index", 0))
    if not verification["valid"]:
        return None
    if (report.get("step_id") != record["source"]
            or any(report.get(key) != payload.get(key) for key in ("argument", "objective", "blocked"))
            or [item.get("statement") for item in report.get("claims", [])]
            != [item.get("statement") for item in payload["claims"]]):
        return None
    source_id = reasoner_report_call(
        state, record["source"], report, record["plan_version"], record["attempt_index"],
        before_revision=review.get("request_revision", -1),
    )
    return report if source_id == checkpoint.get("call_id") else None
