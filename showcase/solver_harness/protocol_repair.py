"""One bounded, identity-independent format repair for known protocol failures.

The planner (``plan_generation``) and the explore entry pioneered this under
the ``star_routing`` gate: a fully received reply that failed the response
protocol is a known failure — never an unknown remote outcome — and a product
run may re-ask the same role once with a fresh call identity and an explicit
repair instruction (#70 bounded recovery). Repair reservations go through the
same counters and S3 admission; a second failure re-raises so each caller's
honest termination semantics stay untouched. Bare (ungated) harness runs keep
the single-attempt behavior.
"""

from .calls import CallInterrupted

KNOWN_RESPONSE_FAILURES = {
    "invalid_json", "invalid_role_schema", "empty_response", "truncated_response",
}

REPAIR_INSTRUCTION = (
    "The previous reply was complete but not valid protocol JSON. Re-issue "
    "your reply as one strict JSON object matching the schema; return the "
    "actual answer values, never the schema definition itself. Preserve the "
    "mathematical claims, necessary proof details, verdict and any executable "
    "tool request with its code and arguments; repair serialization only, "
    "without shortening proofs or changing the requested action. Encode "
    "backslashes, quotes and newlines with valid JSON escapes, including "
    "inside mathematical text and code strings. Do not add unrelated prose."
)


def repair_enabled(config):
    """Product runs only: the same gate the planner repair uses."""
    if config.get("features", {}).get("serialization_repair") is True:
        return False  # The capability-free candidate owns the only repair credit.
    return config.get("features", {}).get("star_routing") is True


def interrupted_call(harness, run_id, exc):
    """Return the failed call record a CallInterrupted points at, else None."""
    if not isinstance(exc, CallInterrupted):
        return None
    latest = harness.get_run(run_id)
    return latest["state"].get("calls", {}).get(getattr(exc, "call_id", None), {})


def known_protocol_failure(call):
    return (call.get("status") == "protocol_failed"
            and call.get("error_category") in KNOWN_RESPONSE_FAILURES)


def repair_call_id(call_id):
    """Keep historical repair identities readable and deterministic."""
    return f"{call_id}:repair-1"


def completed_call_id(calls, call_id):
    """Follow only this review's retry, repair and computation lineage.

    Tool identities belong to the review root (not necessarily the repaired or
    explicitly retried reply). Never select an unrelated most-recent call.
    """
    from .calls import latest_retry_id

    root = call_id
    original = calls.get(root, {})
    tool_roots = [root]
    seq = 1
    for _ in range(len(calls) + 1):
        resolved = latest_retry_id(calls, call_id)
        current = calls.get(resolved, {})
        if (any(current.get(key) != original.get(key)
                for key in ("role", "run_id"))
                or current.get("request", {}).get("solution_candidate")
                != original.get("request", {}).get("solution_candidate")):
            return call_id
        call_id = resolved
        repaired = repair_call_id(call_id)
        serialized = f"{call_id}:serialization-1"
        if (serialized in calls and current.get("response_ref") is not None
                and calls[serialized].get("request", {}).get("serialization_source")
                == current["response_ref"]):
            repaired = serialized
        candidate = calls.get(repaired, {})
        if (current.get("status") != "completed" and candidate
                and all(candidate.get(key) == original.get(key)
                        for key in ("role", "run_id"))):
            call_id = repaired
            if seq == 1:
                tool_roots.append(repaired)
            continue
        if current.get("status") != "completed" or not isinstance(
                current.get("response", {}).get("tool_request"), dict):
            return call_id
        successor = next((f"{base}:tool-{seq}" for base in tool_roots
                          if f"{base}:tool-{seq}" in calls), None)
        if successor is None:
            return call_id
        candidate = calls[successor]
        if (any(candidate.get(key) != original.get(key)
                for key in ("role", "run_id"))
                or candidate.get("request", {}).get("solution_candidate")
                != original.get("request", {}).get("solution_candidate")):
            return call_id
        call_id = successor
        seq += 1
    return call_id


def reserve_repair(harness, run_id, exc, *, failure_event, dispatch_event=None):
    """Record one known failure and reserve its next action on the same ledger.

    Owners call this only for their first response failure. Planner structure
    repair remains in plan_generation: it validates dependencies and versions,
    not just the response protocol. Dispatch remains at the owner boundary so
    its exception/termination semantics are unchanged.
    S3 still owns admission, cancellation, deadline and actual billing.
    """
    failed = interrupted_call(harness, run_id, exc)
    if (failed is None or not repair_enabled(harness._config)
            or not known_protocol_failure(failed)):
        raise exc
    latest = harness.get_run(run_id)
    noted = harness.commit_event(
        run_id, expected_revision=latest["state_revision"],
        event=failure_event(latest, failed), state_updates={"status": "running"})
    if dispatch_event is None:
        return noted  # Finalization reserves through its existing dispatch wrapper.
    return harness.commit_event(
        run_id, expected_revision=noted["state_revision"], event=dispatch_event,
        state_updates={"counters": {
            **noted["state"]["counters"],
            "model_calls": noted["state"]["counters"]["model_calls"] + 1}})


def repair_request(request, *, instruction=REPAIR_INSTRUCTION):
    """A fresh identity for the same question: ``:repair-1`` plus instruction."""
    return {**request, "call_id": repair_call_id(request["call_id"]),
            "repair_instruction": instruction}
