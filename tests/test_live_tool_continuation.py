from __future__ import annotations

import unittest

from showcase.adapters import InternAgentAdapter, InternModelAdapter, ModelResponse
from showcase.graph import AgentDecision, LangGraphExecutionLoop, LoopBudget, ToolExecutionResult


class FakeClient:
    model = "intern-test"

    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return next(self.responses)


class DeterministicContinuation:
    mode = "fake"

    def __init__(self):
        self.calls = []

    def continue_(self, messages, tool_request, tool_result):
        self.calls.append((messages, tool_request, tool_result))
        return ModelResponse(text="候选根有效，最终答案是 1", model_id="intern-test")


class LiveToolContinuationContractTest(unittest.TestCase):
    def test_valid_polynomial_request_executes_and_continues_with_linked_evidence(self):
        continuation = DeterministicContinuation()
        adapter = InternAgentAdapter(
            InternModelAdapter(FakeClient([
                '{"tool_call":{"name":"polynomial_check","arguments":{"schema_version":1,"variable":"x","coefficients":["1","-1"],"domain":{"kind":"real"},"candidates":["1"]}}}',
            ])),
            continuation_transport=continuation,
        )
        loop = LangGraphExecutionLoop(
            adapter,
            _OneTool(ToolExecutionResult.success(value={"candidate_status": "pass"}, result_summary="pass")),
            budget=LoopBudget(max_tools=1),
        )

        result = loop.run({"run_id": "run_live_fake", "problem": "x=1"})

        self.assertEqual("COMPLETED", result["status"])
        self.assertIn("最终答案", result["final_response"])
        self.assertEqual(1, len(continuation.calls))
        self.assertEqual("polynomial_check", continuation.calls[0][1].name)
        self.assertEqual("tool_request_1", result["tool_results"][0]["request_id"])
        self.assertEqual("tool_request_1", result["tool_results"][0]["continuation_request_id"])
        self.assertEqual("fake", result["tool_results"][0]["transport_mode"])

    def test_required_without_tool_request_is_review(self):
        loop = LangGraphExecutionLoop(
            _Agent([AgentDecision.final("答案")]),
            _OneTool(ToolExecutionResult.success()),
        )
        result = loop.run({"run_id": "run_required", "problem": "题目", "verification_mode": "required"})
        self.assertEqual("NEEDS_REVIEW", result["status"])
        self.assertEqual("tool_evidence_missing", result["error"]["category"])

    def test_second_tool_request_after_continuation_is_review(self):
        loop = LangGraphExecutionLoop(
            _Agent([AgentDecision.tool("polynomial_check", {}), AgentDecision.tool("polynomial_check", {})]),
            _OneTool(ToolExecutionResult.success()),
            budget=LoopBudget(max_tools=2),
        )
        result = loop.run({"run_id": "run_over", "problem": "题目"})
        self.assertEqual("NEEDS_REVIEW", result["status"])
        self.assertEqual("continuation_tool_request_exceeded", result["error"]["category"])


class _Agent:
    def __init__(self, decisions):
        self.decisions = iter(decisions)

    def decide(self, _state):
        return next(self.decisions)


class _OneTool:
    def __init__(self, result):
        self.result = result

    def invoke(self, _name, _arguments):
        return self.result


if __name__ == "__main__":
    unittest.main()
