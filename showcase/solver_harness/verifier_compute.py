"""Verifier-initiated controlled computations and the reviewed continuation.

A Verifier reply may propose one finite computation through ``tool_request``.
The runtime — never the reviewer's own text — executes it through the existing
Registry, isolated executor and shared S3 ledger, records an auditable receipt,
and re-dispatches the same review session with that receipt. A pending or
denied request is never parsed as an acceptance verdict or an evidence upgrade.
"""

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy

from .calls import CallInterrupted, latest_retry_id
from .tool_precheck import SAFE_TOOLS, _execute

DEFAULT_MAX_VERIFIER_TOOL_REQUESTS = 2
KNOWN_RESPONSE_FAILURES = {
    "invalid_role_schema", "invalid_json", "empty_response", "truncated_response",
}


def configured_bound(config):
    """Bounded number of verifier computations per review; misconfig clamps safely."""
    value = config.get("max_verifier_tool_requests", DEFAULT_MAX_VERIFIER_TOOL_REQUESTS)
    return value if type(value) is int and 0 <= value <= 16 else DEFAULT_MAX_VERIFIER_TOOL_REQUESTS


def declared_request(reply):
    """Return the computable request, ``{}`` for a malformed one, ``None`` if absent."""
    if not isinstance(reply, Mapping) or not isinstance(reply.get("tool_request"), Mapping):
        return None
    request = reply["tool_request"]
    if (
        request.get("tool") not in SAFE_TOOLS
        or not isinstance(request.get("arguments"), Mapping)
        or request.get("scope") != "finite_computation"
    ):
        return {}
    clean = {
        "tool": request["tool"],
        "arguments": deepcopy(dict(request["arguments"])),
        "scope": "finite_computation",
    }
    if "expected_output" in request:
        clean["expected_output"] = deepcopy(request["expected_output"])
    return clean


def request_digest(request):
    payload = json.dumps(request, sort_keys=True, ensure_ascii=False, default=repr)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verifier_receipts(state, *, role, step_id, round_number, attempt_index):
    """Receipts of this reviewer's own computations inside the same review scope."""
    return [
        receipt
        for receipt in state.get("tool_receipts", [])
        if isinstance(receipt, Mapping)
        and receipt.get("source_role") == role
        and receipt.get("step_id") == step_id
        and receipt.get("review_round", 0) == round_number
        and receipt.get("attempt_index", 0) == attempt_index
    ]


def execute_request(harness, run, *, request, role, step_id, round_number, attempt_index, seq,
                    review_call_id, receipt_prefix="verifier-tool"):
    """Run one reviewer computation on the shared precheck path with review identity."""
    extras = {
        "source_role": role,
        "review_round": round_number,
        "attempt_index": attempt_index,
        "review_call_id": review_call_id,
        "request_index": seq,
        "request_digest": request_digest(request),
    }
    return _execute(
        harness, run, request, harness._config, harness._tool_port, step_id, seq,
        receipt_prefix=receipt_prefix, receipt_extras=extras, commit_state_receipts=True,
    )


def continue_review(harness, run, *, role, step_id, round_number, attempt_index, base_call_id,
                    base_request, reply, reserve_and_dispatch, reply_from=None,
                    receipt_prefix="verifier-tool"):
    """Resolve computation requests, then continue the review with real receipts.

    Returns ``(run, reply, unfulfilled)``. ``reply`` is the last reviewer reply;
    ``unfulfilled`` marks a pending or repeated request the bound refused to
    execute, and the caller must not parse that reply as an acceptance verdict.
    Known protocol failures on the continuation return ``reply=None``; unknown
    outcomes raise.
    """
    request = declared_request(reply)
    if request is None:
        return run, reply, False
    if not request:
        # A declaration the runtime cannot execute must never become a verdict.
        return run, reply, True
    digest = request_digest(request)
    state = run["state"]
    receipts = verifier_receipts(
        state, role=role, step_id=step_id, round_number=round_number, attempt_index=attempt_index)
    matching = next((item for item in receipts if item.get("request_digest") == digest), None)
    if matching is None:
        if len(receipts) >= configured_bound(harness._config):
            return run, reply, True
        run, matching = execute_request(
            harness, run, request=request, role=role, step_id=step_id, round_number=round_number,
            attempt_index=attempt_index, seq=len(receipts), review_call_id=base_call_id,
            receipt_prefix=receipt_prefix)
    elif reply_from is not None:
        # The reviewer repeated an already-answered request instead of continuing.
        return run, reply, True
    call_id = f"{base_call_id}:tool-{matching['request_index'] + 1}"
    report = dict(base_request.get("report") or {})
    report["tool_receipts"] = [
        *report.get("tool_receipts", []),
        *(item for item in verifier_receipts(
            run["state"], role=role, step_id=step_id, round_number=round_number,
            attempt_index=attempt_index)),
    ]
    continuation = {**deepcopy(dict(base_request)), "call_id": call_id, "report": report}
    try:
        run, reply = reserve_and_dispatch(run, matching["request_index"], call_id, continuation)
    except CallInterrupted:
        latest = harness.get_run(run["run_id"])
        calls = latest["state"].get("calls", {})
        call = calls.get(latest_retry_id(calls, call_id), {})
        if call.get("error_category") not in KNOWN_RESPONSE_FAILURES:
            raise
        return latest, None, False
    return continue_review(
        harness, run, role=role, step_id=step_id, round_number=round_number,
        attempt_index=attempt_index, base_call_id=base_call_id, base_request=base_request,
        reply=reply, reserve_and_dispatch=reserve_and_dispatch, reply_from=call_id,
        receipt_prefix=receipt_prefix)
