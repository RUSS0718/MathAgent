"""Public STAR Job regression for explicit handoff after challenged steps."""

import unittest

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import StarJobFixture
from tests.test_star_product_planning import FEATURES, STEP
from tests.test_star_product_tools import NEED_PLAN, PLAN

CHALLENGE = {
    "goal_gate": "PARTIAL",
    "logic_gate": "UNCERTAIN",
    "verdict": "CHALLENGE",
    "objection": "The supplied argument does not establish the claim.",
}


class StarHandoffDeliveryJobTest(StarJobFixture, unittest.TestCase):
    def test_two_challenges_reach_final_reject_with_bound_engineering_delivery(self):
        plan = {
            **PLAN,
            "steps": [
                *PLAN["steps"],
                {"step_id": "check", "title": "Use the sum",
                 "objective": "Use the sum to conclude", "depends_on": ["sum"]},
            ],
        }
        first = {**STEP, "argument": "Unproven draft for sum",
                 "claims": [{"statement": "QUESTIONED_FACT_sum", "label": "hard-verify", "tool_evidence_refs": []}]}
        second = {**STEP, "argument": "Unproven draft for check",
                  "claims": [{"statement": "QUESTIONED_FACT_check", "label": "hard-verify", "tool_evidence_refs": []}]}
        self.open_star(
            [NEED_PLAN, plan, first, CHALLENGE, second, CHALLENGE,
             {"final_response": "A complete answer with unresolved claims."},
             {"verdict": "REJECT", "reason": "The answer relies on unsupported claims."}],
            SHOWCASE_STAR_ACCEPTANCE_MODE="handoff",
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                max_model_calls=16, max_http_attempts=16
            ),
        )

        job_id = self.create_job()
        job = self.terminal(job_id)

        self.assertEqual("failed", job["status"], job)
        result = job["result"]
        self.assertEqual("needs_review", result["verification"]["acceptance"])
        self.assertEqual(
            {"contract": "handoff-delivery-v1", "status": "PASS",
             "math_review": "rejected", "binding": "same_artifact"},
            result["engineering_delivery"],
        )
        self.assertIsNone(result["solver"]["best_effort"])
        findings = self.report(job_id)["checks"]["history"][-1]["findings"]
        self.assertIn("llm_whole_review_reject", findings)
        self.assertEqual(
            ["explore", "planner", "reasoner", "step_verifier",
             "reasoner", "step_verifier", "final_generator", "whole_solution_verifier"],
            [request["role"] for request in self.outbound],
        )

        next_step = self.outbound[4]
        self.assertEqual(1, len(next_step["reviewed_drafts"]))
        self.assertEqual("sum", next_step["reviewed_drafts"][0]["step_id"])
        self.assertEqual("CHALLENGE", next_step["reviewed_drafts"][0]["review"]["verdict"])
        final, whole = self.outbound[-2:]
        self.assertEqual(2, len(final["reviewed_drafts"]))
        self.assertEqual(final["reviewed_drafts"], whole["reviewed_drafts"])
        for request in (final, whole):
            self.assertEqual([], request["accepted_results"])
            self.assertNotIn("QUESTIONED_FACT_sum", str(request["accepted_results"]))
            self.assertNotIn("QUESTIONED_FACT_check", str(request["accepted_results"]))


if __name__ == "__main__":
    unittest.main()
