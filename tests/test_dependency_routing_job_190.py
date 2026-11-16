"""Dependency routing through the real public Job and provider HTTP seams."""

from copy import deepcopy
import os
import unittest
from unittest.mock import patch

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, SOLVED, StarJobFixture
from tests.test_faithful_s03_job import CAPACITY_POLICY, ENDPOINT, SPEC


class DependencyRoutingJobTest(StarJobFixture, unittest.TestCase):
    def test_dependencies_plan_before_solving_and_execute_ordered_work_units(self):
        spec = deepcopy(SPEC)
        spec["root_obligations"].append({
            "obligation_id": "root:conclusion", "obligation_type": "universal",
            "statement": "Use the evaluated value", "prerequisite_ids": ["root:value"],
        })
        plan = {"version": 1, "steps": [
            {"step_id": "value", "title": "evaluate", "objective": "evaluate 1+1",
             "obligation_ids": ["root:value"], "auxiliary_goal_ids": [], "method_id": "direct"},
            {"step_id": "conclusion", "title": "conclude", "objective": "use the value",
             "obligation_ids": ["root:conclusion"], "auxiliary_goal_ids": [],
             "depends_on": ["value"], "method_id": "direct"},
        ]}

        def reply(request):
            role = request["role"]
            if role == "planner":
                return plan
            if role == "reasoner":
                return {"argument": "1+1=2", "claims": [{"statement": "1+1=2",
                        "label": "hard-verify"}], "blocked": False}
            if role == "step_verifier":
                obligation = "root:value" if request["step"]["step_id"] == "value" else "root:conclusion"
                return {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                        "objection": "", "obligation_evidence": [{"obligation_id": obligation,
                        "evidence_category": "universal_proof", "claim_indexes": [0]}]}
            if role == "final_generator":
                return {"final_response": "2"}
            if role == "explore":
                return {**SOLVED, "solution_candidate": "1+1=2"}
            return ACCEPT

        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        self.open_star([spec, *([reply] * 10)],
            SHOWCASE_STAR_ROUTING_POLICY_VERSION="objective-dependency-routing-v1",
            SHOWCASE_STAR_FEATURES=dict.fromkeys({"adaptive_solving", "auto_problem_spec",
                "problem_spec", "final_generation", "final_solution_review", "context_pack",
                "progress_scheduling"}, True),
            SHOWCASE_STAR_CONTEXT_CAPACITY=CAPACITY_POLICY,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=12, max_http_attempts=12))
        job_id = self.create_job()
        final = self.terminal(job_id)
        roles = [request["role"] for request in self.outbound]
        self.assertEqual("planner", roles[1], roles)
        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual(["problem_intake", "planner", "reasoner", "step_verifier",
                          "reasoner", "step_verifier", "final_generator",
                          "whole_solution_verifier"], roles)
        self.assertEqual(["value", "conclusion"], [request["step"]["step_id"]
                         for request in self.outbound if request["role"] == "reasoner"])
        self.assertEqual("2", final["result"]["final_response"])
        events = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        self.assertIn("objective_dependencies", events)
        budget = final["result"]["budget"]
        self.report(job_id)
        self.assertEqual(budget, self.job(job_id)["result"]["budget"])
        self.assertEqual(8, len(self.outbound))
