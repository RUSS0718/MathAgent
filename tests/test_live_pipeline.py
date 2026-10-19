from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from showcase.adapters import ModelResponse, ToolRequest
from showcase.live_pipeline import LiveAgentPipeline, PipelineBudget
from showcase.server import create_live_pipeline
from showcase.tools import ToolRegistry


class ScriptedModel:
    model_id = "intern-test"

    def __init__(self, responses: list[ModelResponse]) -> None:
        self.responses = iter(responses)
        self.calls: list[tuple[list[dict[str, str]], tuple[dict[str, object], ...]]] = []

    def complete(self, messages, *, tools=(), metadata=None):
        del metadata
        self.calls.append((list(messages), tuple(dict(tool) for tool in tools)))
        return next(self.responses)


class LivePipelineContractTest(unittest.TestCase):
    def test_live_defaults_use_long_slot_budget_without_touching_official_path(self) -> None:
        budget = PipelineBudget()

        self.assertGreaterEqual(budget.max_runtime_seconds, 1_000.0)
        self.assertGreaterEqual(budget.max_model_calls, 6)
        self.assertGreaterEqual(budget.max_tool_calls, 2)

    def test_live_factory_reads_showcase_budget_overrides(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SHOWCASE_PIPELINE_MAX_RUNTIME_SECONDS": "321",
                "SHOWCASE_PIPELINE_MAX_MODEL_CALLS": "7",
                "SHOWCASE_PIPELINE_MAX_TOOL_CALLS": "3",
                "SHOWCASE_INTERN_MAX_TOKENS": "12000",
                "SHOWCASE_INTERN_TIMEOUT_SECONDS": "240",
                "SHOWCASE_INTERN_RETRY_COUNT": "3",
            },
            clear=False,
        ):
            pipeline = create_live_pipeline()

        self.assertEqual(321.0, pipeline.budget.max_runtime_seconds)
        self.assertEqual(7, pipeline.budget.max_model_calls)
        self.assertEqual(3, pipeline.budget.max_tool_calls)
        self.assertEqual(12000, pipeline.model.max_tokens)
        self.assertEqual(240, pipeline.model.client_timeout)
        self.assertEqual(3, pipeline.model.client_retry)

    def test_pipeline_runs_roles_and_publishes_redacted_node_events(self) -> None:
        model = ScriptedModel([
            ModelResponse(text="先整理已知条件，再求解并复核。", model_id="intern-test"),
            ModelResponse(text="x=1", model_id="intern-test"),
            ModelResponse(text="答案：x=1。", model_id="intern-test"),
        ])
        registry = ToolRegistry()
        pipeline = LiveAgentPipeline(model, registry)
        events: list[dict[str, object]] = []

        result = pipeline.run("run_live", "求解 x+1=2", emit=events.append)

        self.assertEqual("COMPLETED", result["status"])
        self.assertEqual("答案：x=1。", result["final_response"])
        node_names = {str(event.get("node_name")) for event in events}
        self.assertTrue({"intake", "planner", "solver", "verifier", "synthesizer", "terminal"}.issubset(node_names))
        self.assertTrue(any(event.get("type") == "final_result" for event in events))
        self.assertNotIn("求解 x+1=2", str(events))
        self.assertIn("简体中文", model.calls[-1][0][0]["content"])

    def test_tool_request_uses_tool_node_and_continuation_without_private_value(self) -> None:
        model = ScriptedModel([
            ModelResponse(text="先检查候选根。", model_id="intern-test"),
            ModelResponse(
                text='{"tool_call":{"name":"polynomial_check","arguments":{"schema_version":1,"variable":"x","coefficients":["1","-1"],"domain":{"kind":"real"},"candidates":["1"]}}}',
                tool_requests=(ToolRequest("polynomial_check", {"schema_version": 1, "variable": "x", "coefficients": ["1", "-1"], "domain": {"kind": "real"}, "candidates": ["1"]}),),
                model_id="intern-test",
            ),
            ModelResponse(text="候选根通过。", model_id="intern-test"),
            ModelResponse(text="答案：x=1。", model_id="intern-test"),
        ])
        registry = ToolRegistry()
        registry.register_polynomial_check()
        pipeline = LiveAgentPipeline(model, registry)
        events: list[dict[str, object]] = []

        result = pipeline.run("run_tool", "求解 x^2-1=0", emit=events.append)

        self.assertEqual("COMPLETED", result["status"])
        self.assertIn("tool", {str(event.get("node_name")) for event in events})
        self.assertTrue(any(event.get("type") == "tool_call_result" for event in events))
        self.assertNotIn("_value", str(result))


if __name__ == "__main__":
    unittest.main()
