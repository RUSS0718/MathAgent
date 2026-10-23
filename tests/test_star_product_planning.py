"""Public STAR route and Gate evidence, with only provider HTTP scripted."""

import json
import unittest

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.star_product_support import POLISH, SOLVED
from tests.test_star_product_tools import NEED_PLAN, PLAN, VERDICT

STEP = {"argument": "Addition gives two", "claims": [], "blocked": False}
FEATURES = {"final_generation": True, "final_solution_review": True}


class StarPlanningTest(StarJobFixture, unittest.TestCase):
    def run_plan(self, replies, **config):
        self.open_star(replies, SHOWCASE_STAR_FEATURES=FEATURES,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=16, max_http_attempts=16),
                       **config)
        job_id = self.create_job()
        job = self.terminal(job_id)
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith("data: ")]
        return job_id, job, events

    def test_need_plan_and_accepted_step_expose_actual_gate_decision(self):
        job_id, job, events = self.run_plan([
            NEED_PLAN, PLAN, STEP, VERDICT, {"final_response": "2"}, ACCEPT,
        ])
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(["explore", "planner", "reasoner", "step_verifier",
                          "final_generator", "whole_solution_verifier"],
                         [r["role"] for r in self.outbound])
        gate = next(e for e in events if e.get("solver_event_type") == "step_reviewed")
        self.assertEqual("sum", gate["step_id"])
        self.assertEqual({"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "valid": True},
                         {key: gate[key] for key in ("goal_gate", "logic_gate", "verdict", "valid")})
        self.assertEqual(job_id, gate["solver"]["run_id"])
        self.assertNotIn("Addition gives two", json.dumps(events))

    def test_rejected_exploration_preserves_findings_then_plans(self):
        _, job, events = self.run_plan([
            {**SOLVED, "worked": ["Keep the addition discovery"]}, POLISH,
            {"verdict": "REJECT", "reason": "Needs structured proof"},
            PLAN, STEP, VERDICT, {"final_response": "2"}, ACCEPT,
        ])
        self.assertEqual("succeeded", job["status"], job)
        planner = next(r for r in self.outbound if r["role"] == "planner")
        self.assertEqual("1+1=2", planner["exploration_findings"][0]["solution_candidate"])
        self.assertEqual(["Keep the addition discovery"], planner["exploration_findings"][0]["worked"])
        reviews = [e for e in events if e.get("solver_event_type") == "solution_review_assessed"]
        self.assertEqual("REJECT", reviews[0]["verdict"])
        self.assertEqual("PLAN", reviews[0]["next_phase"])

    def test_partial_meta_retry_is_bounded_then_reaches_planner(self):
        partial = {**NEED_PLAN, "assessment": "PARTIALLY_SOLVED", "worked": ["partial discovery"]}
        _, job, events = self.run_plan([
            partial, {"decision": "RETRY", "reason": "One more approach"}, partial,
            PLAN, STEP, VERDICT, {"final_response": "2"}, ACCEPT,
        ])
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(["explore", "meta", "explore", "planner"], [r["role"] for r in self.outbound[:4]])
        self.assertEqual(2, len(self.outbound[3]["exploration_findings"]))
        route = next(e for e in events if e.get("solver_event_type") == "partial_exploration_routed")
        self.assertEqual("RETRY", route["decision"])

    def test_partial_meta_plan_skips_second_explore(self):
        _, job, _ = self.run_plan([
            {**NEED_PLAN, "assessment": "PARTIALLY_SOLVED"},
            {"decision": "PLAN", "reason": "Decompose now"},
            PLAN, STEP, VERDICT, {"final_response": "2"}, ACCEPT,
        ])
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(["explore", "meta", "planner"], [r["role"] for r in self.outbound[:3]])

    def test_unknown_routes_to_planner_without_polishing(self):
        _, job, events = self.run_plan([
            {**NEED_PLAN, "assessment": "UNKNOWN"}, PLAN, STEP, VERDICT,
            {"final_response": "2"}, ACCEPT,
        ])
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(["explore", "planner"], [r["role"] for r in self.outbound[:2]])
        route = next(e for e in events if e.get("solver_event_type") == "explore_assessed")
        self.assertEqual("UNKNOWN", route["assessment"])
        self.assertEqual("PLAN", route["next_phase"])

    def test_invalid_dependency_is_repaired_with_the_actual_invalid_plan(self):
        invalid = {"version": 1, "steps": [{**PLAN["steps"][0], "depends_on": ["sum"]}]}
        _, job, _ = self.run_plan([
            NEED_PLAN, invalid, PLAN, STEP, VERDICT, {"final_response": "2"}, ACCEPT,
        ])
        self.assertEqual("succeeded", job["status"], job)
        repaired = [r for r in self.outbound if r["role"] == "planner"]
        self.assertEqual(2, len(repaired))
        self.assertEqual(1, repaired[1]["repair_attempt"])
        self.assertEqual(invalid, repaired[1]["invalid_plan"])
        self.assertIn("earlier", repaired[1]["validation_error"])
        self.assertEqual(1, len([r for r in self.outbound if r["role"] == "reasoner"]))


if __name__ == "__main__":
    unittest.main()
