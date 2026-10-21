"""Bounded execution and continuation for one registered tool request."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .adapters import AdapterError, InternModelAdapter, ModelContinuationTransport, ModelResponse
from .graph import ToolExecutionResult
from .redaction import redact_text
from .tool_protocol import ToolProtocol, ToolRequest
from .tools import ToolRegistry

EventSink = Callable[[Mapping[str, Any]], None]
NodeEmitter = Callable[..., None]


@dataclass(frozen=True)
class ToolLoopOutcome:
    solver_text: str
    tool_results: tuple[dict[str, Any], ...] = ()
    error_category: str | None = None
    error_summary: str = ""


def run_tool_roundtrip(
    *,
    run_id: str,
    response: ModelResponse,
    messages: Sequence[Mapping[str, Any]],
    registry: ToolRegistry,
    model: InternModelAdapter,
    tool_protocol: ToolProtocol,
    execution_mode: str,
    tool_count: int,
    max_tool_calls: int,
    model_calls: list[int],
    max_model_calls: int,
    sink: EventSink,
    ensure_runtime: Callable[[], None],
    emit_node: NodeEmitter,
) -> ToolLoopOutcome:
    """Validate, execute, and continue a model request while retaining its call ID."""

    requests = list(response.tool_requests)
    if response.tool_request_error:
        record = _rejected_record(
            run_id, sink, response.tool_protocol, requests[0] if requests else None,
            response.tool_request_error,
        )
        return ToolLoopOutcome("", (record,), response.tool_request_error, "工具请求不符合协议")
    if response.finish_reason == "tool_calls" and not requests:
        record = _rejected_record(run_id, sink, "native", None, "tool_request_invalid")
        return ToolLoopOutcome("", (record,), "tool_request_invalid", "Solver 工具请求不完整")
    if len(requests) > 1:
        records = tuple(
            _rejected_record(run_id, sink, request.protocol, request, "multiple_tool_requests")
            for request in requests
        )
        return ToolLoopOutcome("", records, "multiple_tool_requests", "Solver 一次只能请求一个工具")
    if not requests:
        return ToolLoopOutcome(response.text.strip())

    request = requests[0]
    error = request.error_category
    if request.protocol != tool_protocol:
        error = error or "tool_protocol_mismatch"
    if error:
        record = _rejected_record(run_id, sink, request.protocol, request, error)
        return ToolLoopOutcome("", (record,), error, "Solver 工具请求无效")
    if tool_count >= max_tool_calls:
        record = _rejected_record(
            run_id, sink, request.protocol, request, "tool_budget_exhausted"
        )
        return ToolLoopOutcome("", (record,), "tool_budget_exhausted", "工具调用超出 Run 预算")

    ensure_runtime()
    emit_node("tool", "数学工具", f"调用 {request.name}", "start")
    sink({
        "type": "tool_call_start",
        "job_id": run_id,
        "step_id": "tool-1",
        "node_name": "tool",
        "title": "数学工具调用",
        "tool_name": request.name,
        "tool_call_id": request.tool_call_id,
        "protocol": request.protocol,
        "argument_keys": sorted(str(key) for key in request.arguments),
    })
    result = registry.invoke(
        request.name, request.arguments, tool_call_id=request.tool_call_id
    )
    if not isinstance(result, ToolExecutionResult):
        return ToolLoopOutcome(
            "", (), "tool_result_invalid", "工具返回结果不符合合同"
        )
    if result.tool_call_id != request.tool_call_id:
        result = ToolExecutionResult(
            status="rejected",
            parameter_summary=result.parameter_summary,
            result_summary="tool_call_id_mismatch",
            error_category="tool_call_id_mismatch",
            duration_seconds=result.duration_seconds,
            tool_call_id=request.tool_call_id,
        )
    record: dict[str, Any] = {
        "request_id": request.tool_call_id,
        "tool_call_id": request.tool_call_id,
        "protocol": request.protocol,
        "name": request.name,
        "status": result.status,
        "parameter_summary": result.parameter_summary,
        "result_summary": _summary(result.result_summary, limit=1_000),
        "error_category": result.error_category,
        "duration_seconds": result.duration_seconds,
        "continuation_status": "not_started",
        "continuation_response_received": False,
    }
    if request.name == "polynomial_check" and isinstance(result.value, Mapping):
        record["value"] = dict(result.value)
    _emit_tool_result(run_id, sink, request, result)
    emit_node(
        "tool", "数学工具", "工具调用完成" if result.status == "success" else "工具调用失败，需要复核",
        "end", status="completed" if result.status == "success" else "failed",
    )
    if result.status != "success":
        return ToolLoopOutcome(
            "", (record,), result.error_category or "tool_failed", "数学工具调用失败，需要复核"
        )
    if model_calls[0] >= max_model_calls:
        record["continuation_status"] = "missing"
        record["continuation_error_category"] = "model_budget_exhausted"
        return ToolLoopOutcome(
            "", (record,), "model_budget_exhausted", "模型调用超出 Run 预算，工具结果未续传"
        )

    continuation = ModelContinuationTransport(model)
    model_calls[0] += 1
    try:
        ensure_runtime()
        record["continuation_tool_call_id"] = request.tool_call_id
        continuation_response = continuation.continue_(
            messages,
            request,
            {
                "tool_call_id": request.tool_call_id,
                "name": request.name,
                "status": record["status"],
                "value": result.value,
                "result_summary": record["result_summary"],
            },
        )
    except AdapterError:
        record["continuation_status"] = "missing"
        record["continuation_error_category"] = "tool_continuation_missing"
        return ToolLoopOutcome(
            "", (record,), "tool_continuation_missing", "模型未返回工具结果 continuation"
        )
    except RuntimeError as exc:
        category = getattr(exc, "category", "pipeline_timeout")
        record["continuation_status"] = "missing"
        record["continuation_error_category"] = category
        return ToolLoopOutcome("", (record,), category, "工具 continuation 未在 Run 时限内完成")
    record["continuation_response_received"] = True

    try:
        ensure_runtime()
    except RuntimeError as exc:
        category = getattr(exc, "category", "pipeline_timeout")
        record["continuation_status"] = "response_received"
        record["continuation_tool_call_id"] = request.tool_call_id
        return ToolLoopOutcome("", (record,), category, "工具 continuation 超出 Run 时限")

    if continuation_response.tool_request_error or continuation_response.tool_requests:
        record["continuation_status"] = "unconsumed"
        record["continuation_error_category"] = "tool_result_not_consumed"
        return ToolLoopOutcome(
            "", (record,), "tool_result_not_consumed", "模型没有消费工具结果并请求了另一个工具"
        )
    solver_text = continuation_response.text.strip()
    if not solver_text:
        record["continuation_status"] = "unconsumed"
        record["continuation_error_category"] = "tool_result_not_consumed"
        return ToolLoopOutcome(
            "", (record,), "tool_result_not_consumed", "模型未消费工具结果并返回答案"
        )
    record.update(
        continuation_tool_call_id=request.tool_call_id,
        continuation_response_received=True,
        continuation_status="response_received",
        transport_mode=execution_mode,
    )
    return ToolLoopOutcome(solver_text, (record,))


def _rejected_record(
    run_id: str,
    sink: EventSink,
    protocol: str | None,
    request: ToolRequest | None,
    error_category: str,
) -> dict[str, Any]:
    tool_call_id = request.tool_call_id if request is not None else ""
    name = request.name if request is not None and request.name else "unknown"
    record = {
        "request_id": tool_call_id,
        "tool_call_id": tool_call_id,
        "protocol": protocol or (request.protocol if request is not None else "unavailable"),
        "name": name,
        "status": "rejected",
        "parameter_summary": "",
        "result_summary": error_category,
        "error_category": error_category,
        "continuation_status": "not_started",
        "continuation_response_received": False,
    }
    sink({
        "type": "tool_call_result",
        "job_id": run_id,
        "step_id": "tool-1",
        "node_name": "tool",
        "title": "数学工具请求已拒绝",
        "tool_name": name,
        "tool_call_id": tool_call_id,
        "protocol": record["protocol"],
        "summary": error_category,
        "status": "rejected",
        "error_category": error_category,
    })
    return record


def _emit_tool_result(
    run_id: str,
    sink: EventSink,
    request: ToolRequest,
    result: ToolExecutionResult,
) -> None:
    sink({
        "type": "tool_call_result",
        "job_id": run_id,
        "step_id": "tool-1",
        "node_name": "tool",
        "title": "数学工具结果",
        "tool_name": request.name,
        "name": request.name,
        "tool_call_id": request.tool_call_id,
        "protocol": request.protocol,
        "summary": _summary(result.result_summary, limit=200),
        "status": result.status,
        "error_category": result.error_category,
    })


def _summary(value: Any, *, limit: int) -> str:
    return " ".join(redact_text(str(value or "")).split())[:limit]


__all__ = ["ToolLoopOutcome", "run_tool_roundtrip"]
