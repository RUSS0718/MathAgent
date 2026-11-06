from __future__ import annotations

import json
import unittest

from showcase.graph import ToolExecutionResult
from showcase.run_budget import (
    RunBudgetLedger,
    RunBudgetLimits,
    bind_budget,
    budgeted_tool,
)


class ToolTimeoutAccountingTest(unittest.TestCase):
    def setUp(self):
        self.run_id = "tool-timeout-accounting"
        self.ledger = RunBudgetLedger()
        self.budget = self.ledger.ensure(self.run_id, RunBudgetLimits())

    def tearDown(self):
        self.ledger.close()

    def invoke(self, result):
        class Registry:
            @budgeted_tool
            def invoke(_self, name, arguments, **kwargs):
                return result

        with bind_budget(self.budget):
            return Registry().invoke("python_math", {})

    def stored_tool_action(self):
        raw = self.ledger.connection.execute(
            "SELECT ledger_json FROM run_budgets WHERE run_id=?", (self.run_id,)
        ).fetchone()[0]
        return next(
            action for action in json.loads(raw)["actions"]
            if action["kind"] == "tool"
        )

    def test_confirmed_executor_timeout_preserves_evidence_without_counting_unknown(self):
        executor_value = {
            "status": "arbitrary untrusted status string",
            "unknown_outcome": False,
            "cleanup_verified": True,
            "executed": True,
            "timeout": True,
            "stdout": "must not be copied into the budget ledger",
        }

        result = self.invoke(ToolExecutionResult(status="timeout", value=executor_value))

        self.assertEqual("timeout", result.status)
        self.assertEqual(0, self.budget.snapshot()["unknown_tool_calls"])
        self.assertEqual(
            {
                "unknown_outcome": False,
                "cleanup_verified": True,
                "executed": True,
                "timeout": True,
            },
            self.stored_tool_action()["execution_evidence"],
        )
        action = self.stored_tool_action()
        self.assertNotIn("status", action["execution_evidence"])
        self.assertNotIn("arbitrary untrusted status string", json.dumps(action))

    def test_unknown_executor_timeout_counts_as_unknown(self):
        self.invoke(ToolExecutionResult(
            status="error",
            value={"status": "unknown_outcome", "unknown_outcome": True,
                   "cleanup_verified": False, "executed": True},
        ))

        self.assertEqual(1, self.budget.snapshot()["unknown_tool_calls"])

    def test_timeout_without_executor_evidence_keeps_legacy_unknown_count(self):
        self.invoke(ToolExecutionResult(status="timeout"))

        action = self.stored_tool_action()
        self.assertNotIn("execution_evidence", action)
        self.assertEqual(1, self.budget.snapshot()["unknown_tool_calls"])

    def test_timeout_without_verified_cleanup_keeps_unknown_count(self):
        self.invoke(ToolExecutionResult(
            status="timeout", value={"unknown_outcome": False, "cleanup_verified": False}
        ))

        self.assertEqual(1, self.budget.snapshot()["unknown_tool_calls"])

    def test_legacy_timeout_action_without_evidence_remains_unknown(self):
        action = {
            "id": "legacy-timeout",
            "kind": "tool",
            "status": "timeout",
            "duration_seconds": 1.0,
        }
        state = {
            "limits": {"max_model_calls": 1, "max_http_attempts": 1,
                       "max_tool_calls": 1, "max_tokens": 100,
                       "max_runtime_seconds": 60},
            "started_at": 1.0,
            "deadline_at": 61.0,
            "actions": [action],
        }
        self.ledger.connection.execute(
            "UPDATE run_budgets SET ledger_json=? WHERE run_id=?",
            (json.dumps(state), self.run_id),
        )
        self.ledger.connection.commit()

        self.assertEqual(1, self.budget.snapshot()["unknown_tool_calls"])


if __name__ == "__main__":
    unittest.main()
