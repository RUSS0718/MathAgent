"""Explicit controller commands for receipt acceptance and conflict review."""

from .proof_graph import ProofGraphValidationError


def _current(harness, run_id, expected_revision, graph_version):
    """Bind commands to the current persisted Run and immutable graph version."""
    run = harness.get_run(run_id)
    graph = run["state"].get("proof_graph") if run else None
    if (not isinstance(graph, dict) or graph.get("current_version") != graph_version
            or run["state_revision"] != expected_revision):
        raise ProofGraphValidationError("stale_graph_command")


def accept_counterexample(harness, run_id, *, expected_revision, graph_version,
                          event_id, attempt_id, receipt_id):
    """Accept only a persisted independent receipt; storage rechecks all sources."""
    _current(harness, run_id, expected_revision, graph_version)
    return harness.commit_event(run_id, expected_revision=expected_revision, event={
        "event_id": event_id, "type": "proof_graph_counterexample_verified",
        "attempt_id": attempt_id, "receipt_id": receipt_id,
    })


def resolve_conflict(harness, run_id, *, expected_revision, graph_version,
                     event_id, proposition_id, review_call_id, ruling):
    """Apply a recorded Verifier ruling without issuing another model call."""
    _current(harness, run_id, expected_revision, graph_version)
    return harness.commit_event(run_id, expected_revision=expected_revision, event={
        "event_id": event_id, "type": "proof_graph_conflict_reviewed",
        "resolution": {"proposition_id": proposition_id,
                       "review_call_id": review_call_id, "ruling": ruling},
    })
