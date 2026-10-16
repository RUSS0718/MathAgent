"""Contract tests for the bounded LangGraph showcase loop."""

from __future__ import annotations

import unittest

from showcase.graph import AgentDecision, LangGraphExecutionLoop, LoopBudget, ToolExecutionResult


class ScriptedAgent:
    def __init__(self, decisions):
        self.decisions = iter(decisions)

    def decide(self, _state):
        return next(self.decisions)


class ScriptedTools:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    def invoke(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        return next(self.results)


class LangGraphLoopTest(unittest.TestCase):
    def test_dynamic_tool_call_then_final_answer(self):
        tools = ScriptedTools([ToolExecutionResult.success(value=2, result_summary="2")])
        loop = LangGraphExecutionLoop(
            ScriptedAgent([AgentDecision.tool("python", {"code": "1+1"}), AgentDecision.final("2")]),
            tools,
        )

        result = loop.run({"run_id": "run_success", "problem": "计算 1+1"})

        self.assertEqual("COMPLETED", result["status"])
        self.assertEqual("completed", result["stage"])
        self.assertEqual("2", result["final_response"])
        self.assertEqual([("python", {"code": "1+1"})], tools.calls)
        self.assertEqual(
            [
                "run_received",
                "agent_decision",
                "tool_completed",
                "agent_decision",
                "verification_completed",
                "run_terminal",
            ],
                         [event["type"] for event in result["events"]])

    def test_tool_failure_is_reviewable_and_resume_keeps_failure_event(self):
        tools = ScriptedTools([
            ToolExecutionResult(status="timeout", error_category="tool_timeout"),
        ])
        loop = LangGraphExecutionLoop(
            ScriptedAgent([AgentDecision.tool("python", {})]),
            tools,
            budget=LoopBudget(max_retries=0),
        )
        first = loop.run({"run_id": "run_retry", "problem": "计算"})
        self.assertEqual("NEEDS_REVIEW", first["status"])
        self.assertEqual("tool_timeout", first["error"]["category"])

        resumed_loop = LangGraphExecutionLoop(
            ScriptedAgent([AgentDecision.final("recovered")]),
            ScriptedTools([]),
        )
        resumed = resumed_loop.resume(first, thread_id="run_retry-resume")
        self.assertEqual("COMPLETED", resumed["status"])
        self.assertEqual("recovered", resumed["final_response"])
        self.assertIn("tool_completed", [event["type"] for event in resumed["events"]])
        self.assertIn("run_resumed", [event["type"] for event in resumed["events"]])

    def test_tool_retry_budget_retries_same_request_then_continues(self):
        tools = ScriptedTools(
            [
                ToolExecutionResult(status="timeout", error_category="tool_timeout"),
                ToolExecutionResult.success(result_summary="2"),
            ]
        )
        loop = LangGraphExecutionLoop(
            ScriptedAgent([AgentDecision.tool("python", {}), AgentDecision.final("2")]),
            tools,
            budget=LoopBudget(max_retries=1),
        )
        result = loop.run({"run_id": "run_retry_budget", "problem": "计算"})
        self.assertEqual("COMPLETED", result["status"])
        self.assertEqual(1, result["retry_count"])
        self.assertIn("tool_retry", [event["type"] for event in result["events"]])

    def test_step_budget_has_terminal_explanation(self):
        loop = LangGraphExecutionLoop(
            ScriptedAgent([AgentDecision.tool("never", {})] * 5),
            ScriptedTools([ToolExecutionResult.success()] * 5),
            budget=LoopBudget(max_steps=2, max_tools=5),
        )
        result = loop.run({"run_id": "run_budget", "problem": "循环"})
        self.assertEqual("FAILED", result["status"])
        self.assertEqual("budget_exhausted", result["error"]["category"])

    def test_tool_event_does_not_persist_arguments_or_returned_values(self):
        secret = "prompt=do-not-store token=abc123 complete-value"
        loop = LangGraphExecutionLoop(
            ScriptedAgent([AgentDecision.tool("python", {"prompt": secret, "value": secret}), AgentDecision.final("ok")]),
            ScriptedTools([ToolExecutionResult.success(value={"prompt": secret, "value": secret}, result_summary=secret)]),
        )
        result = loop.run({"run_id": "run_redaction", "problem": "test"})
        serialized = str(result)
        self.assertNotIn("complete-value", serialized)
        self.assertNotIn("abc123", serialized)
        event = next(item for item in result["events"] if item["type"] == "tool_completed")
        self.assertNotIn("arguments", event)
        self.assertNotIn("value", event)

    def test_checkpoint_does_not_persist_pending_tool_arguments(self):
        checkpoints = []
        loop = LangGraphExecutionLoop(
            ScriptedAgent([AgentDecision.tool("python", {"token": "secret"}), AgentDecision.final("ok")]),
            ScriptedTools([ToolExecutionResult.success(result_summary="1")]),
            checkpoint_sink=lambda _run_id, state: checkpoints.append(state),
        )
        loop.run({"run_id": "run_checkpoint_redaction", "problem": "test"})
        self.assertNotIn("secret", str(checkpoints))
        self.assertTrue(all(not isinstance(state.get("pending_tool"), dict) or "arguments" not in state["pending_tool"] for state in checkpoints))

    def test_required_unknown_checker_does_not_emit_verification_pass(self):
        loop = LangGraphExecutionLoop(
            ScriptedAgent([AgentDecision.tool("polynomial_check", {}), AgentDecision.final("x")]),
            ScriptedTools([ToolExecutionResult.success(value={"candidate_status": "unknown", "coverage_status": "unknown"})]),
        )
        result = loop.run({"run_id": "run_unknown_check", "problem": "test", "verification_mode": "required"})
        event = next(item for item in result["events"] if item["type"] == "verification_completed")
        self.assertEqual("unknown", event["status"])
        self.assertEqual("NEEDS_REVIEW", result["status"])


if __name__ == "__main__":
    unittest.main()
