import unittest

from showcase.run_budget import BudgetExhausted, RunBudgetLedger, RunBudgetLimits


class FinalizationReservationTest(unittest.TestCase):
    def setUp(self):
        self.ledger = RunBudgetLedger()
        self.budget = self.ledger.ensure(
            "run", RunBudgetLimits(max_model_calls=4, max_http_attempts=4, max_tokens=500)
        )
        self.addCleanup(self.ledger.close)

    def reserve(self, *, final_input=40, review_input=60):
        return self.ledger.reserve_finalization_pair(
            "run",
            reservation_id="spec-v1:attempt-0",
            final_input_estimate=final_input,
            final_output_cap=50,
            review_input_estimate=review_input,
            review_output_cap=30,
        )

    def test_pair_is_reserved_atomically_and_consumed_without_double_counting(self):
        self.reserve()
        snapshot = self.budget.snapshot()
        self.assertEqual(2, snapshot["logical_calls"])
        self.assertEqual(2, snapshot["http_attempts"])
        self.assertEqual(180, snapshot["reserved_tokens"])

        call = self.budget.model_call("final_generator")
        timeout = call.before_attempt(
            {
                "attempt_id": "actual-final-http",
                "max_tokens": 50,
                "started_at_utc": "2026-11-08T00:00:00Z",
            },
            35,
        )
        self.assertGreater(timeout, 0)
        after_claim = self.budget.snapshot()
        self.assertEqual(2, after_claim["logical_calls"])
        self.assertEqual(2, after_claim["http_attempts"])
        self.budget.after_attempt(
            {
                "attempt_id": "actual-final-http",
                "status": "success",
                "prompt_tokens": 35,
                "completion_tokens": 20,
                "total_tokens": 55,
            }
        )
        settled = self.budget.snapshot()
        self.assertEqual(2, settled["logical_calls"])
        self.assertEqual(2, settled["http_attempts"])
        self.assertEqual(90, settled["reserved_tokens"])
        self.assertEqual(0, settled["unknown_attempts"])

    def test_pair_rejection_does_not_leave_half_a_reservation(self):
        self.ledger.close()
        self.ledger = RunBudgetLedger()
        self.addCleanup(self.ledger.close)
        self.budget = self.ledger.ensure(
            "small", RunBudgetLimits(max_model_calls=1, max_http_attempts=4, max_tokens=500)
        )
        with self.assertRaises(BudgetExhausted):
            self.ledger.reserve_finalization_pair(
                "small",
                reservation_id="spec-v1:attempt-0",
                final_input_estimate=40,
                final_output_cap=50,
                review_input_estimate=60,
                review_output_cap=30,
            )
        snapshot = self.budget.snapshot()
        self.assertEqual(0, snapshot["logical_calls"])
        self.assertEqual(0, snapshot["http_attempts"])
        self.assertEqual(0, snapshot["reserved_tokens"])

    def test_actual_payload_cannot_exceed_its_reserved_slot(self):
        from showcase.run_budget import BudgetExhausted

        self.reserve()
        call = self.budget.model_call("whole_solution_verifier")
        with self.assertRaises(BudgetExhausted):
            call.before_attempt(
                {
                    "attempt_id": "too-large-review",
                    "max_tokens": 31,
                    "started_at_utc": "2026-11-08T00:00:00Z",
                },
                61,
            )
        snapshot = self.budget.snapshot()
        self.assertEqual(2, snapshot["logical_calls"])
        self.assertEqual(2, snapshot["http_attempts"])


if __name__ == "__main__":
    unittest.main()
