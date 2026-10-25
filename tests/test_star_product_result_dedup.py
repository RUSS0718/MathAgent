"""Stable dual-ledger delivery at the authenticated Job boundary (#83)."""

import json
import time
import unittest

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_star_product_planning import FEATURES
from tests.test_star_product_classified_outcomes import (
    ACCEPT_VERDICT, CONJECTURE, LEMMA, PLAN, SELF_CHALLENGE_CLASSIFIED,
    report,
)
from tests.test_star_product_challenge import META_ABORT
from tests.test_star_product_tools import NEED_PLAN


class StarResultDedupTest(StarJobFixture, unittest.TestCase):
    def run_public(self, replies):
        self.open_star(replies, SHOWCASE_STAR_FEATURES=FEATURES,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                           max_model_calls=20, max_http_attempts=20))
        job_id = self.create_job()
        # Two complete archive/plan cycles can exceed the fixture's eight
        # seconds on a busy Windows host. Bound observation, not solver work.
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            job = self.job(job_id)
            if job["status"] in {"succeeded", "failed", "canceled"}:
                return job_id, job, None
            time.sleep(.02)
        self.fail(f"public STAR observation timed out: {self.job(job_id)}")

    def test_two_replans_deliver_dual_ledger_lemma_once_with_original_proof(self):
        approve = {**META_ABORT, "decision": "APPROVE_REPLAN",
                   "reason_summary": "Use a new route", "plan_summary": "Direct route",
                   "reusable_results": [LEMMA]}
        propose = {"goal_gate": "NO", "logic_gate": "FAIL", "verdict": "PROPOSE_REPLAN",
                   "objection": "Change the route"}
        replacement = lambda version: {"version": version, "steps": [
            {"step_id": f"route{version}", "title": "Direct", "objective": "Finish"}]}
        job_id, job, _ = self.run_public([
            NEED_PLAN, PLAN,
            report("ORIGINAL-LEMMA-PROOF", [{"statement": LEMMA, "label": "hard-verify"}]),
            SELF_CHALLENGE_CLASSIFIED,
            report("ARCHIVED-FAILED-ROUTE"), propose, approve, replacement(2),
            report("SECOND-ARCHIVED-ROUTE"), propose, approve, replacement(3),
            report("FINAL-VALID-PROOF"), ACCEPT_VERDICT,
            {"final_response": "2"}, ACCEPT,
        ])
        self.assertEqual("succeeded", job["status"], job)
        planners = [request for request in self.outbound if request["role"] == "planner"]
        self.assertEqual(3, len(planners))
        for request in planners[1:] + [request for request in self.outbound
                                      if request["role"] in {"final_generator", "whole_solution_verifier"}]:
            facts = request["accepted_results"]
            self.assertEqual(1, sum(fact["statement"] == LEMMA for fact in facts), facts)
            lemma = next(fact for fact in facts if fact["statement"] == LEMMA)
            self.assertEqual("llm_reviewed", lemma["evidence_level"])
            self.assertNotIn(CONJECTURE, [fact["statement"] for fact in facts])
        final = next(request for request in self.outbound if request["role"] == "final_generator")
        self.assertEqual(["FINAL-VALID-PROOF"], [proof["argument"] for proof in final["step_proofs"]])
        self.assertNotIn("ARCHIVED-FAILED-ROUTE", json.dumps(final))
        self.assertEqual(16, len(self.outbound))
        checks = self.report(job_id)["checks"]
        self.assertEqual("same_artifact", checks["binding"])
        self.assertEqual("2", job["result"]["final_response"])


if __name__ == "__main__":
    unittest.main()
