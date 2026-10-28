"""Honest, nonterminal observations for an expired in-flight Job attempt."""

import time


def observe_deadline(payload, attempts, budget):
    """Annotate a persisted active Job without claiming a terminal DB write."""
    if payload.get("status") not in {"queued", "running"} or not budget or not budget.get("unresolved_attempts"):
        return
    for attempt in reversed(attempts):
        deadline = attempt.get("deadline_at")
        category = attempt.get("error_category")
        status = attempt.get("status")
        http_status = attempt.get("http_status")
        unknown = status == "unknown" or (status == "error" and (
            category in {"timeout", "connectivity", "missing_finish_reason", "missing_stream_terminal"}
            or (category == "http_status" and type(http_status) is int and 500 <= http_status < 600)))
        if (unknown and attempt.get("dispatch_status") != "not_submitted"
                and type(deadline) in {int, float} and deadline <= time.time()):
            payload["observation"] = {"state": "deadline_unconfirmed", "terminal_persisted": False,
                                      "attempt_id": attempt.get("attempt_id"), "deadline_at": deadline}
            return
