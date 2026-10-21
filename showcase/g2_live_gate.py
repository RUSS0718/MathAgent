"""Offline-testable protocol profile for the authorized Intern S2 G2 gate."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .adapters import AdapterError, InternModelAdapter, ModelResponse
from .request_attempts import capture_pipeline_attempts
from .tool_loop import run_tool_roundtrip
from .tools import ToolRegistry

G2_MODEL = "intern-s2"
G2_DATASET_VERSION = "g2-public-polynomial-v1"
G2_REPEATS = 2
G2_MAX_GENERATIONS_PER_RUN = 2
G2_MAX_HTTP_ATTEMPTS = 12
G2_MAX_TOKENS_PER_ATTEMPT = 512
G2_CLIENT_TIMEOUT_SECONDS = 30
G2_RUN_TIMEOUT_SECONDS = 75
G2_PROTOCOL_PROMPT_VERSION = "g2-native-tool-v2"
G2_PROMPT_ARGUMENT_EXAMPLE = {
    "schema_version": 1,
    "variable": "x",
    "coefficients": ["1", "-1"],
    "domain": {"kind": "real"},
    "candidates": ["1", "2"],
}


def g2_protocol_schema_sha256() -> str:
    """Fingerprint the exact registered parameter schema sent with G2 calls."""

    registry = ToolRegistry(max_calls=1)
    registry.register_polynomial_check()
    parameters = registry.provider_schemas()[0]["function"]["parameters"]
    encoded = json.dumps(parameters, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class G2Case:
    problem_id: str
    problem: str


G2_CASES = (
    G2Case(
        "poly-x-minus-one",
        "请用已注册的 polynomial_check 检查 x - 1 = 0 的实数候选集合 {1, 2}。",
    ),
    G2Case(
        "poly-x-squared-minus-one",
        "请用已注册的 polynomial_check 检查 x^2 - 1 = 0 的实数候选集合 {-1, 1, 2}。",
    ),
    G2Case(
        "poly-x-squared-minus-three-x-plus-two",
        "请用已注册的 polynomial_check 检查 x^2 - 3x + 2 = 0 的实数候选集合 {1, 2, 3}。",
    ),
)

EventSink = Callable[[Mapping[str, Any]], None]


class G2LivePipeline:
    """One native tool request followed by the shared registered-tool roundtrip."""

    execution_mode = "live"

    def __init__(self, model: InternModelAdapter) -> None:
        if (
            model.model_id != G2_MODEL
            or model.client_retry != 1
            or model.client_timeout != G2_CLIENT_TIMEOUT_SECONDS
            or model.thinking_mode is not True
            or not 1 <= model.max_tokens <= G2_MAX_TOKENS_PER_ATTEMPT
        ):
            raise ValueError("g2_model_budget_invalid")
        self.model = model

    @capture_pipeline_attempts
    def run(
        self,
        run_id: str,
        problem: str,
        *,
        verification_mode: str = "auto",
        emit: EventSink | None = None,
    ) -> dict[str, Any]:
        del verification_mode
        sink = emit or (lambda _event: None)
        state: dict[str, Any] = {
            "run_id": run_id,
            "execution_mode": "live",
            "status": "RUNNING",
            "stage": "tool_request",
            "final_response": None,
            "summary": "G2 native tool protocol run",
            "error": None,
            "tool_results": [],
            "verification": {
                "status": "unknown",
                "findings": ["candidate_check_does_not_prove_complete_solution_set"],
                "checker": "polynomial_check",
            },
            "active_node": "solver",
        }
        _emit_node(sink, run_id, "solver", "模型工具请求", "请求一次原生工具调用", "start")
        registry = ToolRegistry(max_calls=1)
        registry.register_polynomial_check()
        example = json.dumps(
            G2_PROMPT_ARGUMENT_EXAMPLE, ensure_ascii=False, separators=(",", ":")
        )
        messages = [
            {
                "role": "system",
                "content": (
                    f"G2 protocol prompt {G2_PROTOCOL_PROMPT_VERSION}. Use the registered native "
                    "polynomial_check function once for the stated candidate check, following "
                    "its registry schema exactly. The schema in the native tool declaration is "
                    "the authority. For real numbers, domain must be the JSON object "
                    '`{"kind":"real"}`, never a quoted string. For example, schema_version '
                    "is integer 1, variable is a string, and coefficients and candidates are "
                    f"arrays of rational strings; this is a valid shape example: `{example}`. "
                    "Use the example's structure and types, but derive the values from the "
                    "current problem. Do not emit a text_action envelope or repair arguments "
                    "after generation. After the tool result is returned, answer briefly without "
                    "hidden reasoning."
                ),
            },
            {"role": "user", "content": problem},
        ]
        try:
            response = self.model.complete(
                messages,
                tools=registry.provider_schemas(),
                metadata={"role": "solver", "run_id": run_id},
            )
        except AdapterError as exc:
            return _fail(state, sink, run_id, exc.category, "Intern 请求未能完成")
        except Exception as exc:  # noqa: BLE001 - keep provider details out of persisted state
            return _fail(state, sink, run_id, "pipeline_error", type(exc).__name__)

        if not isinstance(response, ModelResponse):
            return _fail(state, sink, run_id, "model_response_invalid", "模型响应不符合合同")
        if response.finish_reason == "length":
            return _fail(state, sink, run_id, "output_truncated", "首轮生成达到输出上限")
        if response.finish_reason == "content_filter":
            return _fail(state, sink, run_id, "content_filtered", "首轮生成被服务过滤")

        has_tool_signal = bool(
            response.tool_requests
            or response.tool_request_error
            or response.finish_reason == "tool_calls"
        )
        if not has_tool_signal:
            return _fail(state, sink, run_id, "tool_request_missing", "没有返回原生工具请求")
        if response.tool_protocol == "native" and response.finish_reason != "tool_calls":
            return _fail(
                state, sink, run_id, "tool_finish_reason_invalid", "原生工具请求未以工具终止原因返回"
            )

        outcome = run_tool_roundtrip(
            run_id=run_id,
            response=response,
            messages=messages,
            registry=registry,
            model=self.model,
            tool_protocol="native",
            execution_mode="live",
            tool_count=0,
            max_tool_calls=1,
            model_calls=[1],
            max_model_calls=G2_MAX_GENERATIONS_PER_RUN,
            sink=sink,
            ensure_runtime=lambda: None,
            emit_node=lambda node, title, summary, phase, **kwargs: _emit_node(
                sink, run_id, node, title, summary, phase, **kwargs
            ),
        )
        state["tool_results"].extend(outcome.tool_results)
        if outcome.error_category:
            return _fail(state, sink, run_id, outcome.error_category, outcome.error_summary)
        if not outcome.tool_results:
            return _fail(state, sink, run_id, "tool_request_missing", "没有执行注册工具")

        tool_result = outcome.tool_results[0]
        if tool_result.get("continuation_finish_reason") == "length":
            return _fail(state, sink, run_id, "output_truncated", "工具结果 continuation 被截断")
        if tool_result.get("continuation_finish_reason") != "stop":
            return _fail(
                state, sink, run_id, "continuation_finish_reason_unknown", "continuation 终止状态未知"
            )

        state.update(
            status="COMPLETED",
            stage="completed",
            final_response=outcome.solver_text,
            summary="G2 native tool protocol roundtrip recorded",
            active_node="terminal",
        )
        _emit_node(sink, run_id, "terminal", "终态", "协议回路已记录", "end", status="completed")
        sink({
            "type": "final_result",
            "job_id": run_id,
            "node_name": "terminal",
            "step_id": "terminal",
            "title": "任务完成",
            "data": {"type": "text", "summary": "已记录工具请求、执行和 continuation 响应"},
        })
        return state


def _fail(
    state: dict[str, Any], sink: EventSink, run_id: str, category: str, summary: str
) -> dict[str, Any]:
    state.update(
        status="NEEDS_REVIEW",
        stage="failed",
        error={"category": category, "summary": summary, "node_name": "solver"},
        active_node="solver",
    )
    _emit_node(sink, run_id, "solver", "工具闭环复核", summary, "end", status="failed")
    sink({
        "type": "error",
        "job_id": run_id,
        "node_name": "solver",
        "step_id": "solver-error",
        "title": "Run 需要复核",
        "message": category,
    })
    return state


def _emit_node(
    sink: EventSink,
    run_id: str,
    node_name: str,
    title: str,
    summary: str,
    phase: str,
    *,
    status: str | None = None,
) -> None:
    event_type = "node_start" if phase == "start" else "node_end"
    event: dict[str, Any] = {
        "type": event_type,
        "job_id": run_id,
        "step_id": node_name,
        "node_name": node_name,
        "title": title,
        "summary": summary,
    }
    if status is not None:
        event["status"] = status
    sink(event)


__all__ = [
    "G2_CASES",
    "G2_CLIENT_TIMEOUT_SECONDS",
    "G2_DATASET_VERSION",
    "G2_MAX_GENERATIONS_PER_RUN",
    "G2_MAX_HTTP_ATTEMPTS",
    "G2_MAX_TOKENS_PER_ATTEMPT",
    "G2_MODEL",
    "G2_PROMPT_ARGUMENT_EXAMPLE",
    "G2_PROTOCOL_PROMPT_VERSION",
    "G2_REPEATS",
    "G2_RUN_TIMEOUT_SECONDS",
    "G2Case",
    "G2LivePipeline",
    "g2_protocol_schema_sha256",
]
