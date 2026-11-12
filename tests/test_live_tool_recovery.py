"""Local Python guard rejection must reach a bounded solver repair round."""

import json
import unittest
from unittest.mock import patch

from showcase.adapters import AdapterError, ModelResponse, ToolRequest
from showcase.live_pipeline import LiveAgentPipeline, PipelineBudget
from showcase.run_budget import BudgetExhausted
from showcase.tools import ToolRegistry
from tests.test_live_pipeline import ScriptedModel


class LiveToolRecoveryTest(unittest.TestCase):
    def test_guard_rejection_can_return_an_answer(self):
        model = ScriptedModel([
            ModelResponse(text="计划"),
            ModelResponse(tool_requests=(ToolRequest(
                "python_math", {"code": "import sympy as sp\nx=sp.Symbol('x')\nprint(x.diff(x))"},
                tool_call_id="rejected-1", protocol="native",
            ),), finish_reason="tool_calls"),
            ModelResponse(text="不用工具，导数为 1。"),
            ModelResponse(text="导数为 1，工具被拒绝，未经验证。"),
        ])
        registry = ToolRegistry()
        registry.register_python_math()
        result = LiveAgentPipeline(model, registry).run("run-repair", "求 x 的导数")
        self.assertTrue(result["final_response"])
        self.assertEqual(4, len(model.calls))
        self.assertEqual("rejected", result["tool_results"][0]["status"])
        self.assertEqual("call_not_allowed", result["tool_results"][0]["error_category"])
        self.assertNotEqual("pass", result["verification"]["status"])

    def run_repair(self, repair, *, protocol="native", budget=None, registry=None, response_text=""):
        request = ToolRequest("python_math", {"code": "print(broken.diff())"},
                              tool_call_id="first-rejected", protocol=protocol,
                              assistant_content="private tool action")
        model = ScriptedModel([
            ModelResponse(text="计划"),
            ModelResponse(text=response_text, tool_requests=(request,), finish_reason="tool_calls"),
            repair, ModelResponse(text="计算后得到候选答案"), ModelResponse(text="公开答案"),
        ])
        registry = registry or ToolRegistry()
        registry.register_python_math()
        events = []
        result = LiveAgentPipeline(model, registry, tool_protocol=protocol, budget=budget).run(
            "run-repair", "题目", emit=events.append,
        )
        return result, model, events

    def test_native_rejection_retains_assistant_text_with_call_and_receipt(self):
        marker = "assistant-context-marker"
        result, model, _ = self.run_repair(ModelResponse(text="候选答案"), response_text=marker)
        history = model.calls[2][0]
        assistant = next(message for message in history if message.get("tool_calls"))
        self.assertEqual(marker, assistant["content"])
        self.assertEqual("first-rejected", assistant["tool_calls"][0]["id"])
        self.assertTrue(result["final_response"])
        self.assertEqual("rejected", result["tool_results"][0]["status"])

    def test_repaired_code_executes_with_both_receipts_and_history(self):
        for protocol in ("native", "text_action"):
            repair = ModelResponse(tool_requests=(ToolRequest(
                "python_math", {"code": "import sympy as sp\nprint(sp.diff(sp.Symbol('x'), sp.Symbol('x')))"},
                tool_call_id="corrected-2", protocol=protocol, assistant_content="corrected action",
            ),), finish_reason="tool_calls")
            with self.subTest(protocol=protocol):
                result, model, events = self.run_repair(repair, protocol=protocol)
                self.assertTrue(result["final_response"])
                self.assertEqual(["rejected", "success"], [r["status"] for r in result["tool_results"]])
                self.assertIn("first-rejected", json.dumps(model.calls[3][0]))
                self.assertIn("corrected-2", json.dumps(model.calls[3][0]))
                self.assertEqual(5, len(model.calls))
                self.assertNotIn("broken.diff", json.dumps(events))

    def test_second_rejection_stops_without_looping(self):
        repair = ModelResponse(tool_requests=(ToolRequest(
            "python_math", {"code": "print(other.diff())"}, tool_call_id="second-rejected",
            protocol="native",
        ),), finish_reason="tool_calls")
        result, model, _ = self.run_repair(repair)
        self.assertFalse(result["final_response"])
        self.assertEqual(3, len(model.calls))
        self.assertEqual(2, len(result["tool_results"]))

    def test_model_budget_blocks_repair(self):
        result, model, _ = self.run_repair(ModelResponse(text="answer"),
                                          budget=PipelineBudget(max_model_calls=2))
        self.assertFalse(result["final_response"])
        self.assertEqual(2, len(model.calls))
        self.assertEqual("rejected", result["tool_results"][0]["status"])

    def test_tool_budget_blocks_corrected_dispatch(self):
        repair = ModelResponse(tool_requests=(ToolRequest(
            "python_math", {"code": "print(1)"}, tool_call_id="corrected-2", protocol="native",
        ),), finish_reason="tool_calls")
        result, model, _ = self.run_repair(repair, budget=PipelineBudget(max_tool_calls=1))
        self.assertFalse(result["final_response"])
        self.assertEqual(3, len(model.calls))
        self.assertEqual("tool_budget_exhausted", result["tool_results"][-1]["error_category"])

    def test_repair_budget_exception_keeps_rejection_receipt(self):
        original = ScriptedModel.complete

        def complete(model, messages, **kwargs):
            if len(model.calls) == 2:
                raise BudgetExhausted("stop")
            return original(model, messages, **kwargs)

        with patch.object(ScriptedModel, "complete", complete):
            result, _, _ = self.run_repair(ModelResponse(text="answer"))
        self.assertFalse(result["final_response"])
        self.assertEqual("rejected", result["tool_results"][0]["status"])
        self.assertEqual("run_budget_exhausted", result["error"]["category"])

    def test_unknown_repair_transport_stops_without_resending(self):
        original = ScriptedModel.complete
        attempted = []

        def complete(model, messages, **kwargs):
            if len(model.calls) == 2:
                attempted.append(True)
                raise AdapterError("unknown_outcome")
            return original(model, messages, **kwargs)

        with patch.object(ScriptedModel, "complete", complete):
            result, _, _ = self.run_repair(ModelResponse(text="answer"))
        self.assertEqual([True], attempted)
        self.assertFalse(result["final_response"])
        self.assertEqual("rejected", result["tool_results"][0]["status"])
        self.assertEqual("tool_continuation_missing", result["error"]["category"])

