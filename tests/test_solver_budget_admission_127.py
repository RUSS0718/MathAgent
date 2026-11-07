"""A local admission rejection terminates as budget exhaustion, not remote unknown."""

import unittest

from showcase.run_budget import BudgetExhausted
from showcase.solver_harness import SolverHarness


class SolverBudgetAdmissionTest(unittest.TestCase):
    def test_rejected_model_admission_is_known_budget_terminal(self):
        class Port:
            def complete(self, request):
                raise BudgetExhausted("run_model_budget_exhausted")

        with SolverHarness(config={"features": {"stream_recovery": True}}, model_port=Port()) as harness:
            run = harness.solve("Compute", {"run_id": "local-budget-stop"})
        self.assertEqual("partial_budget_exhausted", run["state"]["status"])
        self.assertEqual("TERMINAL", run["state"]["phase"])
        self.assertEqual("shared_admission_budget_exhausted", run["state"]["budget"]["exhaustion_reason"])
        call = next(iter(run["state"]["calls"].values()))
        self.assertEqual("budget_rejected", call["status"])
        self.assertNotIn("unknown_outcome", [a["status"] for a in run["state"]["calls"].values()])
