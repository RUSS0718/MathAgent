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


def repair_request(request, *, instruction=REPAIR_INSTRUCTION):
    """A fresh identity for the same question: ``:repair-1`` plus instruction."""
    return {**request, "call_id": f"{request['call_id']}:repair-1",
            "repair_instruction": instruction}
