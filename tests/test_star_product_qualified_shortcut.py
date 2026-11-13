"""Scalar Explore answers cannot discharge typed proof obligations."""

import json
import unittest

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, SOLVED, StarJobFixture
from tests.test_star_population_runtime import PROBLEM, SPEC


class QualifiedShortcutJobTest(StarJobFixture, unittest.TestCase):
    def test_scalar_with_completeness_obligation_retains_finding_then_plans(self):
        problem = "Count the positive divisors of 6 and prove the list is complete."
        solution = "6=2×3, so its positive divisors are exactly 1, 2, 3, 6. There are 4."
        spec = {
            "specification_version": 1, "original_problem": problem,
            "domain": "positive integers", "quantifiers": [], "assumptions": [],
            "directions": ["enumeration", "completeness"],
            "output_requirements": ["count", "completeness proof"],
            "root_obligations": [
                {"obligation_id": "count", "obligation_type": "enumeration",
                 "statement": "Count the positive divisors."},
                {"obligation_id": "proof", "obligation_type": "completeness",
                 "statement": "Prove every positive divisor is listed."},
            ], "auxiliary_goals": [],
        }
        plan = {"version": 1, "steps": [{
            "step_id": "divisors", "title": "Count and justify", "objective": problem,
            "obligation_ids": ["count", "proof"], "auxiliary_goal_ids": [],
        }]}
        step = {"argument": solution, "blocked": False,
                "claims": [{"statement": solution, "label": "easy-verify"}]}
        review = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                  "objection": "", "obligation_evidence": [
                      {"obligation_id": root, "evidence_category": category, "claim_indexes": [0]}
                      for root, category in (("count", "enumeration_result"),
                                             ("proof", "completeness_proof"))]}
        self.open_star([
            spec, {**SOLVED, "solution_candidate": "4", "worked": ["counted divisors"]},
            {"solution_candidate": "4"}, ACCEPT, plan, step, review,
            {"final_response": solution}, ACCEPT,
        ], SHOWCASE_STAR_FEATURES={"auto_problem_spec": True, "problem_spec": True,
                                  "final_generation": True, "final_solution_review": True},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=9, max_http_attempts=9))
        response = self.client.post("/api/agent/jobs", headers=self.headers(), json={
            "message": problem, "session_id": self.session, "solver_mode": "star_limited"})
        self.assertEqual(202, response.status_code, response.get_json())
        job_id = response.get_json()["job_id"]
        job = self.terminal(job_id)
        self.assertIn("planner", [request["role"] for request in self.outbound])
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(solution, job["result"]["final_response"])
        planner = next(request for request in self.outbound if request["role"] == "planner")
        finding = planner["exploration_findings"][0]
        self.assertEqual("4", finding["solution_candidate"])
        self.assertEqual(["counted divisors"], finding["worked"])
        self.assertEqual(spec, planner["problem_spec"])
        self.assertEqual({job_id}, {request["run_id"] for request in self.outbound})
        budget = self.report(job_id)["budget"]
        self.assertEqual(9, budget["logical_calls"])
        self.assertEqual(9, budget["http_attempts"])
        self.assertEqual(9, budget["limits"]["max_model_calls"])
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith("data: ")]
        rejected = next(event for event in events
                        if event.get("solver_event_type") == "solution_review_assessed")
        self.assertEqual("REJECT", rejected["verdict"])
        self.assertEqual("PLAN", rejected["next_phase"])

    def test_scalar_numerical_spec_keeps_complete_explore_shortcut(self):
        self.open_star([SPEC, SOLVED, {"solution_candidate": "2"}, ACCEPT],
            SHOWCASE_STAR_FEATURES={"auto_problem_spec": True, "problem_spec": True,
                                   "final_generation": True, "final_solution_review": True},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=4, max_http_attempts=4))
        response = self.client.post("/api/agent/jobs", headers=self.headers(), json={
            "message": PROBLEM, "session_id": self.session, "solver_mode": "star_limited"})
        self.assertEqual(202, response.status_code, response.get_json())
        job_id = response.get_json()["job_id"]
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual("2", job["result"]["final_response"])
        self.assertEqual(["problem_intake", "explore", "explore_polish", "whole_solution_verifier"],
                         [request["role"] for request in self.outbound])
        self.assertEqual(4, self.report(job_id)["budget"]["logical_calls"])
