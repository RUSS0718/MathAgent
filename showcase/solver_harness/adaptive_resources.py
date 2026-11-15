"""Serial adaptive calls leave room for independent review and bounded repair."""

import math
import time
from contextlib import contextmanager
from contextvars import ContextVar

_allocation = ContextVar("adaptive_resource_allocation", default=None)
VERSION = "adaptive-resources-v1"


def current_floor(run_id):
    value = _allocation.get()
    return value[1] if value is not None and value[0] == run_id else {}


@contextmanager
def bind_allocation(run_id, floor):
    token = _allocation.set((run_id, floor))
    try:
        yield
    finally:
        _allocation.reset(token)


def allocate(harness, run, request):
    """Estimate the next stage from the current payload, without charging usage."""
    from ..run_budget import current_budget
    from .finalize import (
        _serialized_request_size,
        finalization_requests,
        finalization_reserve_estimate,
        proof_basis,
        valid_facts,
    )

    state = run["state"]
    shared = current_budget()
    if (shared is None or state.get("adaptive_resource_policy") != VERSION
            or not state.get("adaptive_solving")
            or request.get("finalization_scope") is True
            or state.get("population_policy", {}).get("enabled") is True):
        return {}, None
    port = harness._model_port
    adapter = getattr(port, "adapter", None)
    cap = getattr(adapter, "max_tokens", None)
    client_getter = getattr(adapter, "_get_client", None)
    client = client_getter() if callable(client_getter) else None
    timeout = getattr(client, "timeout", None) or getattr(adapter, "client_timeout", None)
    retries = getattr(client, "retry", None)
    if (type(cap) is not int or cap <= 0 or type(timeout) not in {int, float}
            or not math.isfinite(timeout) or timeout <= 0
            or type(retries) is not int or retries < 0):
        return {}, "adaptive_resource_estimate_unavailable"
    try:
        size = _serialized_request_size(harness, port, run, request, use_snapshot=True) + 1024
        generator, review = finalization_requests(
            request.get("problem", getattr(port, "original_problem", "")),
            valid_facts(state), proof_basis(state), f"reserve:{run['run_id']}", None, False)
        closing = finalization_reserve_estimate(
            harness, port, run, generator, review, require_cap=True, use_snapshot=True)
    except Exception:
        return {}, "adaptive_resource_estimate_unavailable"
    role = request["role"]
    if role == "whole_solution_verifier":
        calls, tokens = 0, 0
    elif role in {"explore", "final_generator"}:
        calls, tokens = 1, closing["review_input"] + cap
    else:
        calls, tokens = 2, closing["tokens"]
    # One shared repair cushion, not an indefinitely renewed per-call allowance.
    # Empty/truncated replies also get repair_instruction, without format_repair.
    repair_used = bool(request.get("repair_instruction")) or any(
        call.get("request", {}).get("repair_instruction")
        and call.get("role") != "problem_intake"
        for call in state.get("calls", {}).values())
    if not repair_used:
        calls += 1
        tokens += size + 4 * cap + 1024 + cap
    floor = {"model_calls": calls, "http_attempts": calls, "tokens": tokens,
             "time_seconds": calls * timeout * (retries + 1)}
    snapshot = shared.snapshot()
    limits = snapshot["limits"]
    deadline = snapshot["deadline_at"] - floor["time_seconds"]
    if (snapshot["logical_calls"] + 1 + calls > limits["max_model_calls"]
            or snapshot["http_attempts"] + 1 + calls > limits["max_http_attempts"]
            or snapshot["charged_tokens"] + size + cap + tokens > limits["max_tokens"]
            or time.time() >= deadline):
        return floor, "adaptive_closing_reserve_required"
    # This is a scoped work deadline, never a replacement for the root deadline.
    floor["work_deadline_at"] = deadline
    return floor, None
