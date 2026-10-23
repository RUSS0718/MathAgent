"""Real Registry work in the STAR worker must use its original S3 context."""

import unittest

from showcase.run_budget import RunBudgetLimits, current_budget
from showcase.tools import ToolRegistry
from tests.star_product_support import ACCEPT, StarJobFixture

NEED_PLAN = {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []}
PLAN = {"version": 1, "steps": [{"step_id": "sum", "title": "Add", "objective": "Compute 1+1"}]}
STEP = {"argument": "addition", "blocked": False, "claims": [{
    "statement": "1+1=2", "label": "easy-verify", "tool_request": {
        "tool": "polynomial_check", "arguments": {}, "scope": "finite_computation",
        "expected_output": 2}}]}
VERDICT = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": ""}
FEATURES = {"final_generation": True, "final_solution_review": True, "local_code_tool": True}


class StarToolTest(StarJobFixture, unittest.TestCase):
    def test_registry_precheck_thread_charges_original_run_once(self):
        actual = []
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda args: actual.append(
            current_budget().run_id if current_budget() else None) or 2)
        self.open_star([NEED_PLAN, PLAN, STEP, VERDICT, {"final_response": "1+1=2"}, ACCEPT],
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8, max_tool_calls=2),
            SHOWCASE_STAR_FEATURES=FEATURES, SHOWCASE_STAR_REGISTRY=registry)
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual([job_id], actual, job)
        self.assertEqual(1, self.report(job_id)["budget"]["tool_calls"])
        self.assertEqual(6, self.report(job_id)["budget"]["logical_calls"])
        self.assertEqual(6, len(self.outbound))
        review = next(r for r in self.outbound if r["role"] == "step_verifier")
        self.assertEqual("verified", review["report"]["claims"][0]["label"])
        self.assertEqual("succeeded", job["status"], job)


if __name__ == "__main__":
    unittest.main()
