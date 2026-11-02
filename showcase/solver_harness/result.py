"""Explicit result boundary for Showcase; never imported by the official agent."""

from collections.abc import Mapping

from ..redaction import redact


def export_result(snapshot):
    """Return only the allowed ``final_response`` field from a run or state."""
    if not isinstance(snapshot, Mapping):
        raise ValueError("snapshot must be a run envelope or state mapping")
    state = snapshot.get("state", snapshot)
    if not isinstance(state, Mapping):
        raise ValueError("snapshot.state must be a mapping")
    answer = state.get("final_response")
    if not isinstance(answer, str) or not answer.strip():
        answer = "No complete answer is available for this run."
    return {"final_response": redact(answer)}
