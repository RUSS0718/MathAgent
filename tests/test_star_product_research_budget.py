"""Existing Meta/research phases cross the same product S3 Adapter boundary."""

import threading
import unittest

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_star_product_tools import NEED_PLAN, PLAN, VERDICT

PLAIN_STEP = {"argument": "1+1=2", "blocked": False, "claims": []}
REPLAN_VERDICT = {**VERDICT, "verdict": "PROPOSE_REPLAN", "objection": "Try a new plan"}
DECISION = {"decision": "APPROVE_REPLAN", "reason_summary": "Change method",
            "plan_summary": "Add", "forbidden_directions": [], "reusable_results": [], "trace_back_to": None}
DELEGATE = {"tasks": [{"prompt": "Check addition without code", "permitted_tools": [], "timeout_seconds": 2}]}
REPLIES = [NEED_PLAN, PLAN, PLAIN_STEP, REPLAN_VERDICT, DECISION, DELEGATE,
           {"findings": ["Addition is enough"]}, {**PLAN, "version": 2}, PLAIN_STEP,
           VERDICT, {"final_response": "2"}, ACCEPT]
FEATURES = {"final_generation": True, "final_solution_review": True, "reexplore_after_replan": True}


class StarResearchBudgetTest(StarJobFixture, unittest.TestCase):
    def test_cancel_research_keeps_late_usage_without_further_planner(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def late(context):
            entered.set()
            release.wait(5)
            return {"findings": ["Late result must never become math"]}

        replies = [*REPLIES[:6], late]
        self.open_star(replies, SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=14, max_http_attempts=14))
        job_id = self.create_job()
        self.assertTrue(entered.wait(5))
        self.cancel(job_id)
        release.set()
        self.wait_for(lambda: self.report(job_id)["budget"]["provider_known"]["total_tokens"] == 70)
        self.assertEqual(7, len(self.outbound))
        self.assertEqual("canceled", self.job(job_id)["status"])
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        self.assertNotIn('"solver_event_type":"research_finished"', stream.replace(" ", ""))
        math = self.client.get(f"/api/runs/{job_id}").get_json()["result"]["solver"]
        self.assertEqual("POST_REPLAN_REEXPLORE", math["phase"])

    def test_model_budget_exhausted_before_meta_does_not_dispatch_it(self):
        self.open_star(REPLIES[:4], SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=4, max_http_attempts=4))
        job_id = self.create_job()
        self.assertEqual("failed", self.terminal(job_id)["status"])
        self.assertEqual(["explore", "planner", "reasoner", "step_verifier"],
                         [request["role"] for request in self.outbound])
        self.assertEqual(4, self.report(job_id)["budget"]["logical_calls"])

    def test_meta_and_threaded_research_share_one_cumulative_job_ledger(self):
        self.open_star(REPLIES, SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=14, max_http_attempts=14))
        job_id = self.create_job()
        job = self.terminal(job_id)
        roles = [request["role"] for request in self.outbound]
        self.assertIn("meta", roles, job)
        self.assertIn("researcher", roles, job)
        self.assertEqual(12, len(roles), roles)
        self.assertTrue(all(request["run_id"] == job_id for request in self.outbound))
        research = next(request for request in self.outbound if request["role"] == "researcher")
        self.assertEqual([], research["allowed_tools"])
        self.assertEqual([], research["tool_policy"]["allow"])
        report = self.report(job_id)
        self.assertEqual(12, report["budget"]["logical_calls"])
        self.assertEqual(12, report["budget"]["http_attempts"])
        self.assertEqual(120, report["budget"]["provider_known"]["total_tokens"])
        self.assertEqual("succeeded", job["status"], job)


if __name__ == "__main__":
    unittest.main()
