"""Bounded live Agent pipeline used by the v0.2 workspace.

The pipeline keeps model prompts and tool values inside the live execution
boundary. Only short, redacted node summaries are sent to the workspace event
store and the browser.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .adapters import (
    AdapterError,
    InternModelAdapter,
    ModelContinuationTransport,
    ModelResponse,
    ToolRequest,
    _valid_polynomial_request,
)
from .graph import ToolExecutionResult
from .redaction import redact_text
from .tools import ToolRegistry
from .verification import LightweightVerificationHook

EventSink = Callable[[Mapping[str, Any]], None]


@dataclass(frozen=True)
class PipelineBudget:
    """Independent live budget; it is deliberately smaller than a full agent runtime."""

    max_model_calls: int = 4
    max_tool_calls: int = 1
    max_runtime_seconds: float = 90.0


class PipelineFailure(RuntimeError):
    """A safe, public category for one live pipeline failure."""

    def __init__(self, category: str, summary: str, *, review: bool = False) -> None:
        super().__init__(category)
        self.category = category
        self.summary = summary
        self.review = review


class LiveAgentPipeline:
    """Run the product roles and expose each role as a public node event."""

    def __init__(
        self,
        model: InternModelAdapter,
        registry: ToolRegistry,
        *,
        verifier: LightweightVerificationHook | None = None,
        budget: PipelineBudget | None = None,
    ) -> None:
        self.model = model
        self.registry = registry
        self.verifier = verifier or LightweightVerificationHook()
        self.budget = budget or PipelineBudget()

    def run(
        self,
        run_id: str,
        problem: str,
        *,
        verification_mode: str = "auto",
        emit: EventSink | None = None,
    ) -> dict[str, Any]:
        """Execute one bounded live run and return JSON-compatible product state."""

        sink = emit or (lambda _event: None)
        started = time.monotonic()
        model_calls = [0]
        state: dict[str, Any] = {
            "run_id": run_id,
            "status": "RUNNING",
            "stage": "intake",
            "final_response": None,
            "summary": "实时模型流水线已完成",
            "error": None,
            "tool_results": [],
            "verification": {"status": "unknown", "findings": ["verification_not_run"]},
            "active_node": "intake",
        }
        try:
            clean_problem = self._intake(run_id, problem, sink)
            state["active_node"] = "planner"
            plan = self._planner(run_id, clean_problem, sink, started, model_calls)
            state["active_node"] = "solver"
            solver_response, _solver_messages = self._solver(
                run_id, clean_problem, plan, sink, started, state, model_calls
            )
            state["active_node"] = "verifier"
            verification = self._verifier(
                run_id,
                solver_response,
                state["tool_results"],
                verification_mode,
                sink,
                started,
            )
            state["verification"] = verification
            state["active_node"] = "synthesizer"
            final_response = self._synthesizer(
                run_id,
                clean_problem,
                plan,
                solver_response,
                verification,
                sink,
                started,
                model_calls,
            )
            state["final_response"] = final_response
            if verification_mode == "required" and verification.get("status") != "pass":
                raise PipelineFailure(
                    "verification_needs_review",
                    "Required verification did not produce a complete pass",
                    review=True,
                )
            state["status"] = "COMPLETED"
            state["stage"] = "completed"
            state["active_node"] = "terminal"
            self._emit_node(sink, run_id, "terminal", "终态", "任务已完成", "start")
            self._emit_node(sink, run_id, "terminal", "终态", "任务已完成", "end", status="completed")
            sink({
                "type": "final_result",
                "job_id": run_id,
                "node_name": "terminal",
                "step_id": "terminal",
                "title": "任务完成",
                "data": {"type": "text", "summary": "公开答案已生成"},
            })
        except PipelineFailure as exc:
            state["status"] = "NEEDS_REVIEW" if exc.review else "FAILED"
            state["stage"] = "failed"
            state["error"] = {
                "category": exc.category,
                "summary": exc.summary,
                "node_name": state.get("active_node", "pipeline"),
            }
            self._emit_node(
                sink,
                run_id,
                _failed_node(state),
                "失败节点",
                exc.summary,
                "end",
                status="failed",
            )
            sink({
                "type": "error",
                "job_id": run_id,
                "node_name": _failed_node(state),
                "step_id": f"{_failed_node(state)}-error",
                "title": "任务需要复核",
                "message": exc.category,
            })
        except AdapterError as exc:
            state["status"] = "NEEDS_REVIEW"
            state["stage"] = "failed"
            state["error"] = {
                "category": exc.category,
                "summary": "Intern adapter unavailable",
                "node_name": state.get("active_node", "pipeline"),
            }
            failed_node = _failed_node(state)
            self._emit_node(
                sink,
                run_id,
                failed_node,
                "模型连接",
                "Intern API 调用未完成",
                "end",
                status="failed",
            )
            sink({
                "type": "error",
                "job_id": run_id,
                "node_name": failed_node,
                "step_id": f"{failed_node}-error",
                "title": "模型连接失败",
                "message": exc.category,
            })
        except Exception as exc:  # noqa: BLE001 - public boundary normalizes provider failures
            state["status"] = "FAILED"
            state["stage"] = "failed"
            state["error"] = {
                "category": "pipeline_error",
                "summary": type(exc).__name__,
                "node_name": state.get("active_node", "pipeline"),
            }
            failed_node = _failed_node(state)
            self._emit_node(
                sink,
                run_id,
                failed_node,
                "运行链路",
                "live pipeline 执行失败",
                "end",
                status="failed",
            )
            sink({
                "type": "error",
                "job_id": run_id,
                "node_name": failed_node,
                "step_id": f"{failed_node}-error",
                "title": "运行失败",
                "message": "pipeline_error",
            })
        return state

    def _intake(self, run_id: str, problem: str, sink: EventSink) -> str:
        self._emit_node(sink, run_id, "intake", "整理题目", "开始整理输入", "start")
        clean = problem.strip()
        if not clean:
            self._emit_node(sink, run_id, "intake", "整理题目", "题目为空", "end", status="failed")
            raise PipelineFailure("empty_problem", "题目不能为空")
        self._emit_node(
            sink,
            run_id,
            "intake",
            "整理题目",
            f"已接收文本题（{len(clean)} 字符）",
            "end",
            status="completed",
        )
        return clean

    def _planner(
        self,
        run_id: str,
        problem: str,
        sink: EventSink,
        started: float,
        model_calls: list[int],
    ) -> str:
        self._ensure_runtime(started)
        self._emit_node(sink, run_id, "planner", "规划器", "请求 Intern 生成解题计划", "start")
        response = self._complete(
            role="planner",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the Planner role in a math agent. Return a short public plan "
                        "with knowns, target, and a verification idea. Do not reveal hidden reasoning."
                    ),
                },
                {"role": "user", "content": problem},
            ],
            call_counter=model_calls,
        )
        plan = response.text.strip()
        if not plan:
            raise PipelineFailure("planner_empty", "Planner 返回空结果")
        plan = _summary(plan, limit=1200)
        self._emit_node(sink, run_id, "planner", "规划器", "已生成有限解题计划", "end", status="completed")
        return plan

    def _solver(
        self,
        run_id: str,
        problem: str,
        plan: str,
        sink: EventSink,
        started: float,
        state: dict[str, Any],
        model_calls: list[int],
    ) -> tuple[str, list[dict[str, Any]]]:
        self._ensure_runtime(started)
        self._emit_node(sink, run_id, "solver", "求解器", "根据计划生成候选答案", "start")
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the Solver role in a math agent. Return a concise candidate answer. "
                    "When exact polynomial candidate checking is useful, return one JSON tool_call "
                    "using the registered schema. Do not reveal hidden reasoning."
                ),
            },
            {"role": "user", "content": f"题目：{problem}\n计划摘要：{plan}"},
        ]
        response = self._complete(
            role="solver",
            messages=messages,
            tools=self.registry.describe(),
            call_counter=model_calls,
        )
        requests = list(response.tool_requests)
        if len(requests) > 1:
            raise PipelineFailure("multiple_tool_requests", "Solver 一次只能请求一个工具", review=True)
        if requests:
            request = requests[0]
            if request.name == "polynomial_check" and not _valid_polynomial_request(request.arguments):
                raise PipelineFailure("tool_request_invalid", "Solver 的多项式工具请求不符合 schema", review=True)
            if len(state["tool_results"]) >= self.budget.max_tool_calls:
                raise PipelineFailure("tool_budget_exhausted", "工具调用超出 live pipeline 预算", review=True)
            state["active_node"] = "tool"
            tool_record, tool_value = self._run_tool(run_id, request, sink, started)
            state["tool_results"].append(tool_record)
            continuation = ModelContinuationTransport(self.model)
            if model_calls[0] >= self.budget.max_model_calls:
                raise PipelineFailure("model_budget_exhausted", "模型调用超出 live pipeline 预算", review=True)
            model_calls[0] += 1
            state["active_node"] = "solver"
            continuation_response = continuation.continue_(
                messages,
                request,
                {
                    "name": request.name,
                    "status": tool_record["status"],
                    "value": tool_value,
                    "result_summary": tool_record.get("result_summary", ""),
                },
            )
            if continuation_response.tool_requests:
                raise PipelineFailure(
                    "continuation_tool_request_exceeded",
                    "Solver continuation 又请求了工具",
                    review=True,
                )
            solver_text = continuation_response.text.strip()
            tool_record["continuation_request_id"] = tool_record["request_id"]
            tool_record["transport_mode"] = continuation.mode
        else:
            solver_text = response.text.strip()
        if not solver_text:
            raise PipelineFailure("solver_empty", "Solver 返回空结果")
        self._emit_node(sink, run_id, "solver", "求解器", "已生成候选答案", "end", status="completed")
        return solver_text, messages

    def _run_tool(
        self,
        run_id: str,
        request: ToolRequest,
        sink: EventSink,
        started: float,
    ) -> tuple[dict[str, Any], Any]:
        self._ensure_runtime(started)
        self._emit_node(sink, run_id, "tool", "数学工具", f"调用 {request.name}", "start")
        sink({
            "type": "tool_call_start",
            "job_id": run_id,
            "step_id": "tool-1",
            "node_name": "tool",
            "title": "数学工具调用",
            "tool_name": request.name,
            "argument_keys": sorted(str(key) for key in request.arguments),
        })
        result = self.registry.invoke(request.name, request.arguments)
        if not isinstance(result, ToolExecutionResult):
            raise PipelineFailure("tool_result_invalid", "工具返回结果不符合合同", review=True)
        record: dict[str, Any] = {
            "request_id": "tool_request_1",
            "name": request.name,
            "status": result.status,
            "parameter_summary": result.parameter_summary,
            "result_summary": _summary(result.result_summary, limit=1000),
            "error_category": result.error_category,
            "duration_seconds": result.duration_seconds,
        }
        if result.status != "success":
            self._emit_node(sink, run_id, "tool", "数学工具", "工具调用失败，需要复核", "end", status="failed")
            raise PipelineFailure(result.error_category or "tool_failed", "数学工具调用失败", review=True)
        sink({
            "type": "tool_call_result",
            "job_id": run_id,
            "step_id": "tool-1",
            "node_name": "tool",
            "title": "数学工具结果",
            "tool_name": request.name,
            "name": request.name,
            "summary": _summary(result.result_summary, limit=200),
            "status": result.status,
        })
        self._emit_node(sink, run_id, "tool", "数学工具", "工具调用完成", "end", status="completed")
        return record, result.value

    def _verifier(
        self,
        run_id: str,
        candidate: str,
        tool_results: Sequence[Mapping[str, Any]],
        verification_mode: str,
        sink: EventSink,
        started: float,
    ) -> dict[str, Any]:
        self._ensure_runtime(started)
        self._emit_node(sink, run_id, "verifier", "验证器", "检查答案与工具证据", "start")
        public_results = [{key: value for key, value in item.items() if key != "_value"} for item in tool_results]
        result = self.verifier.verify({"final_response": candidate}, public_results)
        verification = {
            "status": result.status,
            "findings": list(result.findings),
            "checker": result.checker,
        }
        summary = f"验证状态：{result.status}"
        if verification_mode == "required" and result.status != "pass":
            summary += "（required 模式将进入复核）"
        self._emit_node(sink, run_id, "verifier", "验证器", summary, "end", status="completed")
        return verification

    def _synthesizer(
        self,
        run_id: str,
        problem: str,
        plan: str,
        candidate: str,
        verification: Mapping[str, Any],
        sink: EventSink,
        started: float,
        model_calls: list[int],
    ) -> str:
        self._ensure_runtime(started)
        self._emit_node(sink, run_id, "synthesizer", "综合器", "组织公开答案与验证说明", "start")
        response = self._complete(
            role="synthesizer",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是数学智能体的综合器。必须只用简体中文输出最终公开答案，使用清晰的 Markdown 结构："
                        "## 推导、## 答案、## 验证与局限。可以使用 $...$ 或 $$...$$ 表示公式。"
                        "答案要简洁、可读，并明确说明验证证据的边界；不要输出英文标题、完整提示或隐藏推理。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "problem": problem,
                            "plan_summary": plan,
                            "candidate": candidate,
                            "verification": dict(verification),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            call_counter=model_calls,
        )
        final = response.text.strip()
        if not final:
            raise PipelineFailure("synthesizer_empty", "Synthesizer 返回空结果")
        self._emit_node(sink, run_id, "synthesizer", "综合器", "已生成公开答案与验证说明", "end", status="completed")
        return final

    def _complete(
        self,
        *,
        role: str,
        messages: list[dict[str, str]],
        tools: Sequence[Mapping[str, Any]] = (),
        call_counter: list[int],
    ) -> ModelResponse:
        if call_counter[0] >= self.budget.max_model_calls:
            raise PipelineFailure("model_budget_exhausted", "模型调用超出 live pipeline 预算", review=True)
        call_counter[0] += 1
        response = self.model.complete(messages, tools=tools, metadata={"role": role})
        if not isinstance(response, ModelResponse):
            raise PipelineFailure("model_response_invalid", f"{role} 返回结果不符合合同")
        return response

    def _ensure_runtime(self, started: float) -> None:
        if time.monotonic() - started >= self.budget.max_runtime_seconds:
            raise PipelineFailure("pipeline_timeout", "live pipeline 超出运行预算", review=True)

    @staticmethod
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
        payload: dict[str, Any] = {
            "type": event_type,
            "job_id": run_id,
            "step_id": node_name,
            "node_name": node_name,
            "title": title,
            "summary": _summary(summary),
        }
        if status is not None:
            payload["status"] = status
        if phase == "end":
            payload["duration"] = 0.0
        sink(payload)


def _failed_node(state: Mapping[str, Any]) -> str:
    error = state.get("error")
    if isinstance(error, Mapping) and isinstance(error.get("node_name"), str):
        return str(error["node_name"])
    active = state.get("active_node")
    if isinstance(active, str) and active:
        return active
    category = str(error.get("category", "pipeline")) if isinstance(error, Mapping) else "pipeline"
    return category.split("_", 1)[0] or "pipeline"


def _summary(value: Any, *, limit: int = 400) -> str:
    text = " ".join(redact_text(str(value or "")).split())
    return text[:limit]


__all__ = ["LiveAgentPipeline", "PipelineBudget", "PipelineFailure"]
