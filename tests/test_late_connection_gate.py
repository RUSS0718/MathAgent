"""Late retries stop within their bound while the shared owner gate is held."""

import tempfile
import threading
import unittest
from pathlib import Path

from showcase.run_budget import RunBudgetLedger, RunBudgetLimits
from showcase.run_budget_late import settle_late_with_retry


class LateConnectionGateTest(unittest.TestCase):
    def test_connection_gate_retry_exhaustion_keeps_original_reservation(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        gate = threading.RLock()
        ledger = RunBudgetLedger(database_path=Path(directory) / "budget.sqlite",
                                 connection_lock=gate)
        self.addCleanup(ledger.close)
        budget = ledger.ensure("late", RunBudgetLimits())
        event = {"attempt_id": "original", "logical_call_id": "logical",
                 "role": "explore", "max_tokens": 32}
        budget.before_attempt(event, 8)
        before = budget.snapshot()
        original_attempts = ledger.attempts("late")
        with gate:
            worker = threading.Thread(target=settle_late_with_retry, args=(budget, {
                **event, "status": "success", "prompt_tokens": 7,
                "completion_tokens": 3, "total_tokens": 10}), daemon=True)
            with self.assertLogs("showcase.run_budget_late", level="WARNING"):
                worker.start()
                worker.join(2)
                self.assertFalse(worker.is_alive(), "late callback waited for the owner gate")
            self.assertEqual(original_attempts, ledger.attempts("late"))
            self.assertEqual(before["reserved_tokens"], budget.snapshot()["reserved_tokens"])
        self.assertEqual(1, len(list(Path(str(ledger.database_path) + ".late-usage")
                                     .joinpath("pending").glob("*.json"))))


if __name__ == "__main__":
    unittest.main()
