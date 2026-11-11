"""Native arms reserve full action-and-review resources before dispatch."""

import json
import unittest

from tests import test_faithful_s10_intervention_execution as support


class NativeBudgetTest(unittest.TestCase):
    setUp = support.InterventionExecutionTest.setUp
    reserve = support.InterventionExecutionTest.reserve
    def test_native_symmetric_action_review_and_tool_holds(self):
        report = self.reserve(reservation={
            "input_estimate": 10, "output_cap": 20, "model_calls": 3,
            "http_attempts": 1, "tool_calls": 1, "time_seconds": 10,
        })
        self.assertEqual(6, report["budget_reservation"]["logical_calls"])
        self.assertEqual(2, report["budget_reservation"]["tool_calls"])
        self.assertEqual(20, report["budget_reservation"]["time_seconds"])

    def test_pair_cannot_consume_parent_closing_reserve(self):
        from showcase.run_budget import BudgetExhausted

        state = dict(self.parent["state"])
        state["route_budget"] = {"closing_reserve": {"model_calls": 7}}
        self.connection.execute("UPDATE solver_states SET state_json=? WHERE run_id=?",
            (json.dumps(state, sort_keys=True, separators=(",", ":")), "parent-run"))
        self.connection.commit()
        with self.assertRaises(BudgetExhausted):
            self.reserve()

    def test_pair_reservation_uses_frozen_intervention_closing_floor(self):
        from showcase.faithful_intervention_control import ensure_control_schema
        from showcase.run_budget import BudgetExhausted

        ensure_control_schema(self.connection)
        self.connection.execute(
            "INSERT INTO faithful_intervention_control "
            "(job_id,run_id,status,closing_reserve_json,updated_at) "
            "VALUES('job-1','parent-run','paused',?,0)",
            (json.dumps({"source": "finalize.finalization_reserve_estimate",
                         "model_calls": 7, "http_attempts": 7, "tokens": 900,
                         "tool_calls": 4, "time_seconds": 30}),),
        )
        self.connection.commit()

        with self.assertRaises(BudgetExhausted):
            self.reserve(reservation={"input_estimate": 10, "output_cap": 20,
                                      "model_calls": 2, "http_attempts": 1,
                                      "tool_calls": 0, "time_seconds": 10})

    def test_native_budget_requires_explicit_positive_time(self):
        from showcase.solver_harness.faithful_intervention_native_budget import native_arm_budget
        from showcase.solver_harness.faithful_intervention_records import FaithfulInterventionError

        report = self.reserve()
        with self.assertRaises(FaithfulInterventionError):
            native_arm_budget(self.ledger, report, "control", self.gate)


if __name__ == "__main__":
    unittest.main()
