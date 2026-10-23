"""Public STAR route and Gate evidence, with only provider HTTP scripted."""

import json
import unittest

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, StarJobFixture
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


if __name__ == "__main__":
    unittest.main()
