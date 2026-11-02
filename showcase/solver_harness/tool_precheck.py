"""Receipt-backed finite-computation prechecks before mathematical review."""

import json
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from contextvars import copy_context
from copy import deepcopy
from datetime import UTC, datetime

from ..redaction import redact
from ..run_budget import current_budget

POLICY_VERSION = "solver-local-precheck-1"
SAFE_TOOLS = frozenset({"polynomial_check", "python_math"})


def precheck_report(harness, run, *, config, tool_port):
    state = run["state"]
    step_id = state.get("current_step")
    record = state.get("steps", {}).get(step_id, {})
    report = deepcopy(record.get("report", {}))
    if not report or report.get("prechecked"):
        return run
    has_request = any(
        claim.get("label") == "easy-verify" and isinstance(claim.get("tool_request"), Mapping)
        for claim in report.get("claims", [])
    )
    if config.get("features", {}).get("local_code_tool") is not True and not has_request:
        return run
    receipts = list(state.get("tool_receipts", []))
    for index, claim in enumerate(report.get("claims", [])):
        if claim.get("label") != "easy-verify":
            continue
        request = claim.pop("tool_request", None)
        retries = config.get("max_tool_retries", 0)
        retries = min(2, max(0, retries)) if type(retries) is int else 0
        for attempt in range(retries + 1):
            receipt = _recover_receipt(harness, run, step_id, index)
            if receipt is None:
                run, receipt = _execute(harness, run, request, config, tool_port, step_id, index)
            receipts.append(receipt)
            if receipt["status"] not in {"tool_error", "network_error"}:
                break
            if attempt == retries:
                break
        refs = [receipt["receipt_id"]]
        claim["tool_evidence_refs"] = refs
        if receipt["assertion_matched"]:
            claim.update(label="verified", verification_scope="finite_computation")
    report["prechecked"] = True
    report["tool_evidence_refs"] = [
        ref for claim in report.get("claims", []) for ref in claim.get("tool_evidence_refs", [])
    ]
    report["tool_receipts"] = [r for r in receipts if r["step_id"] == step_id]
    latest = run["state"]
    return harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={
            "event_id": f"prechecked-{run['state_revision']}",
            "type": "step_prechecked",
            "step_id": step_id,
        },
        state_updates={
            "tool_receipts": receipts,
            "steps": {**latest["steps"], step_id: {**latest["steps"][step_id], "report": report}},
        },
    )


def _recover_receipt(harness, run, step_id, claim_index):
    if not getattr(harness, "_product_recovery", False):
        return None
    reported = max((event["state_revision"] for event in run["events"]
                    if event["type"] == "step_reported" and event.get("step_id") == step_id),
                   default=run["state_revision"])
    for event in reversed(run["events"]):
        receipt = event.get("receipt", {})
        if (event["type"] == "tool_receipt" and event["state_revision"] > reported
                and receipt.get("step_id") == step_id
                and receipt.get("claim_index") == claim_index):
            return deepcopy(receipt)
    return None


def _execute(harness, run, request, config, port, step_id, claim_index, *, receipt_prefix="tool",
             receipt_extras=None, commit_state_receipts=False):
    state = run["state"]
    receipt_id = f"{receipt_prefix}:{run['run_id']}:{run['state_revision']}:{claim_index}"
    receipt = {
        "receipt_id": receipt_id,
        "tool": request.get("tool") if isinstance(request, Mapping) else None,
        "step_id": step_id,
        "claim_index": claim_index,
        "executed": False,
        "status": "not_executed",
        "exit_code": None,
        "output": None,
        "timeout": False,
        "assertion_matched": False,
        "source": "skipped",
        "sandbox_policy_version": POLICY_VERSION,
        "input": None,
        "code_ref": None,
        "stdout_ref": None,
        "stderr_ref": None,
        "unknown_outcome": False,
    }
    if receipt_extras:
        receipt.update(deepcopy(dict(receipt_extras)))
    state_receipts = (
        {"tool_receipts": [*state.get("tool_receipts", []), receipt]}
        if commit_state_receipts
        else None
    )
    reason = _denial(state, run["run_id"], request, config, port)
    if reason:
        receipt["reason"] = reason
        run = harness.commit_event(
            run["run_id"],
            expected_revision=run["state_revision"],
            event={"event_id": receipt_id, "type": "tool_precheck_skipped", "reason": reason},
            state_updates=state_receipts,
        )
        return run, receipt
    timeout = min(float(config.get("tool_timeout_seconds", 3)), _remaining(state, config))
    limit = config.get("max_tool_output_bytes", 16000)
    counters = {**state["counters"], "tool_calls": state["counters"]["tool_calls"] + 1}
    run = harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={
            "event_id": f"{receipt_id}:dispatch",
            "type": "tool_dispatched",
            "tool": request["tool"],
        },
        state_updates={"counters": counters},
    )
    receipt.update(
        executed=True,
        source=port.source,
        input=redact(deepcopy(request["arguments"])),
        code_ref=f"{receipt_id}:input",
        stdout_ref=f"{receipt_id}:output",
    )
    invocation = {
        "run_id": run["run_id"],
        "call_id": receipt_id,
        "tool": request["tool"],
        "arguments": deepcopy(request["arguments"]),
        "timeout_seconds": timeout,
        "max_output_bytes": limit,
    }
    started = time.monotonic()
    pool = ThreadPoolExecutor(max_workers=1)
    managed = getattr(port, "owns_execution_limits", False) and request["tool"] == "python_math"
    future = None if managed else pool.submit(copy_context().run, port.execute, invocation)
    try:
        result = port.execute(invocation) if managed else future.result(timeout=timeout)
        if not isinstance(result, Mapping):
            raise ValueError("malformed_tool_result")
        status = result.get("status")
        output = result.get("output")
        size = len(json.dumps(output, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        receipt["status"] = (
            status
            if status
            in {
                "success",
                "output_limit",
                "canceled",
                "unavailable",
                "timeout",
                "tool_error",
                "network_error",
                "parse_error",
                "unknown_outcome",
                "rejected",
            }
            else "tool_error"
        )
        if not managed and (time.monotonic() - started >= timeout or _remaining(state, config) <= 0):
            receipt.update(
                status="timeout",
                timeout=True,
                unknown_outcome=True,
                reason="execution_outcome_unknown",
            )
        elif size > limit:
            receipt.update(status="output_limit", reason="output_limit_exceeded")
        else:
            receipt.update(output=redact(deepcopy(output)), exit_code=result.get("exit_code"))
        if managed:
            receipt.update({key: result.get(key) for key in ("code_ref", "input_ref", "stdout_ref", "stderr_ref", "receipt_ref", "image", "environment", "sandbox_policy_version", "cleanup_verified", "retained_output_bytes", "observed_output_bytes", "executed", "signal", "oom_killed", "timeout", "unknown_outcome", "termination_reason")})
            receipt["unknown_outcome"] = result.get("unknown_outcome") is True or result.get("status") == "unknown_outcome"
        if (
            receipt["status"] == "success"
            and type(receipt["exit_code"]) is int
            and receipt["exit_code"] == 0
        ):
            receipt["assertion_matched"] = (
                request.get("scope") == "finite_computation"
                and "expected_output" in request
                and json.dumps(output, sort_keys=True, allow_nan=False)
                == json.dumps(request["expected_output"], sort_keys=True, allow_nan=False)
            )
    except (FutureTimeout, TimeoutError):
        receipt.update(
            status="timeout", timeout=True, unknown_outcome=True, reason="execution_outcome_unknown"
        )
    except ConnectionError:
        receipt["status"] = "network_error"
    except (TypeError, ValueError):
        receipt["status"] = "parse_error"
    except Exception:
        receipt["status"] = "tool_error"
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    receipt["timeout"] = receipt.get("timeout") is True or receipt["status"] == "timeout"
    receipt["unknown_outcome"] |= receipt["status"] == "unknown_outcome" or (
        not managed and receipt["status"] == "timeout")
    run = harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={"event_id": receipt_id, "type": "tool_receipt", "receipt": receipt},
        state_updates=state_receipts,
    )
    return run, receipt


def _remaining(state, config):
    shared = current_budget()
    if shared is not None:
        return shared.snapshot()["deadline_at"] - time.time()
    elapsed = (datetime.now(UTC) - datetime.fromisoformat(state["created_at"])).total_seconds()
    return config.get("max_total_duration_seconds", 3600) - elapsed


def _denial(state, run_id, request, config, port):
    if not isinstance(request, Mapping) or not isinstance(request.get("arguments"), Mapping):
        return "not_executed"
    args = request["arguments"]
    if any(key in args and args[key] != run_id for key in ("run_id", "target_run_id")):
        return "cross_run_denied"
    try:
        if len(json.dumps(args, ensure_ascii=False, allow_nan=False).encode("utf-8")) > 32000:
            return "input_limit_exceeded"
    except (TypeError, ValueError):
        return "invalid_arguments"
    tool = request.get("tool")
    if state.get("reasoning_mode") == "reason_noncoding":
        return "pure_reasoning_denied"
    if (
        config.get("features", {}).get("local_code_tool") is not True
        or port is None
        or not isinstance(tool, str)
        or tool not in SAFE_TOOLS
        or tool not in config.get("allowed_tools", [])
        or tool not in port.registered_tools
    ):
        return "tool_not_allowed"
    if _remaining(state, config) <= 0:
        return "runtime_budget_exhausted"
    shared = current_budget()
    used = shared.snapshot()["tool_calls"] if shared else state["counters"]["tool_calls"]
    limit = shared.snapshot()["limits"]["max_tool_calls"] if shared else config.get("max_tool_calls", 8)
    if used >= limit:
        return "tool_call_budget_exhausted"
    if config.get("tool_timeout_seconds", 3) <= 0:
        return "timeout_budget_exhausted"
    if (
        type(config.get("max_tool_output_bytes", 16000)) is not int
        or config.get("max_tool_output_bytes", 16000) <= 0
    ):
        return "output_budget_exhausted"
    return None


def allowed_tool_ids(run, role, config, port):
    """Advertise only registered, explicit, local permissions for this role."""
    if (
        config.get("features", {}).get("local_code_tool") is not True
        or port is None
        or role not in {"reasoner", "step_verifier", "whole_solution_verifier", "explore"}
        or run["state"].get("reasoning_mode") == "reason_noncoding"
    ):
        return []
    return sorted(SAFE_TOOLS & port.registered_tools & set(config.get("allowed_tools", [])))
