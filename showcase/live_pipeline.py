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
    ModelResponse,
)
from .redaction import redact_text
from .request_attempts import capture_pipeline_attempts
from .tool_loop import run_tool_roundtrip
from .tool_protocol import ToolProtocol
from .tools import ToolRegistry
from .verification import LightweightVerificationHook

EventSink = Callable[[Mapping[str, Any]], None]


@dataclass(frozen=True)
class PipelineBudget:
    """Independent live budget aligned with the long Showcase evaluation slot."""

    max_model_calls: int = 6
    max_tool_calls: int = 2
    max_runtime_seconds: float = 1_100.0


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
        tool_protocol: ToolProtocol = "native",
        execution_mode: str = "live",
    ) -> None:
        self.model = model
        self.registry = registry
        self.verifier = verifier or LightweightVerificationHook()
        self.budget = budget or PipelineBudget()
        if tool_protocol not in {"native", "text_action"}:
            raise ValueError("tool_protocol_invalid")
        if execution_mode not in {"live", "fake"}:
            raise ValueError("execution_mode_invalid")
        self.tool_protocol = tool_protocol
        self.execution_mode = execution_mode

    @capture_pipeline_attempts
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
            "execution_mode": self.execution_mode,
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
                    "When a registered tool is useful, request it using the provided protocol. "
                    "Do not reveal hidden reasoning."
                ),
            },
            {"role": "user", "content": f"题目：{problem}\n计划摘要：{plan}"},
        ]
        tools = self.registry.provider_schemas() if self.tool_protocol == "native" else ()
        if self.tool_protocol == "text_action":
            messages[0]["content"] += (
                " Use only the text_action protocol: return JSON with protocol='text_action' "
                "and tool_call containing id, name, and arguments. Registered schemas: "
                + json.dumps(self.registry.allowed_schemas(), ensure_ascii=False, separators=(",", ":"))
            )
        response = self._complete(
            role="solver",
            messages=messages,
            tools=tools,
            call_counter=model_calls,
        )
        outcome = run_tool_roundtrip(
            run_id=run_id,
            response=response,
            messages=messages,
            registry=self.registry,
            model=self.model,
            tool_protocol=self.tool_protocol,
            execution_mode=self.execution_mode,
            tool_count=len(state["tool_results"]),
            max_tool_calls=self.budget.max_tool_calls,
            model_calls=model_calls,
            max_model_calls=self.budget.max_model_calls,
            sink=sink,
            ensure_runtime=lambda: self._ensure_runtime(started),
            emit_node=lambda node_name, title, summary, phase, **kwargs: self._emit_node(
                sink, run_id, node_name, title, summary, phase, **kwargs
            ),
        )
        state["tool_results"].extend(outcome.tool_results)
        if outcome.tool_results:
            state["active_node"] = "tool" if outcome.error_category else "solver"
        if outcome.error_category:
            raise PipelineFailure(outcome.error_category, outcome.error_summary, review=True)
        solver_text = outcome.solver_text
        if not solver_text:
            raise PipelineFailure("solver_empty", "Solver 返回空结果")
        self._emit_node(sink, run_id, "solver", "求解器", "已生成候选答案", "end", status="completed")
        return solver_text, messages

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
