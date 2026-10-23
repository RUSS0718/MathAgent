"""Cancellation at the mathematical commit boundary of actual public STAR Jobs."""

import threading
import time
import unittest
from unittest.mock import patch

from showcase.run_budget import RunBudgetLimits
from showcase.solver_harness.storage import SolverStateStore
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture


class StarControlTest(StarJobFixture, unittest.TestCase):
    def test_late_usage_settles_after_cancel_without_next_role_or_math_progress(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def reply(context):
            entered.set()
            release.wait(5)
            return SOLVED

        self.open_star([reply])
        job_id = self.create_job()
        self.assertTrue(entered.wait(5))
        self.cancel(job_id)
        held = self.report(job_id)["budget"]
        self.assertEqual(1, held["unresolved_attempts"])
        self.assertGreater(held["reserved_tokens"], 0)
        release.set()
        self.wait_for(lambda: self.report(job_id)["budget"]["provider_known"]["total_tokens"] == 10)
        self.assertEqual(1, len(self.outbound))
        self.assertEqual("canceled", self.job(job_id)["status"])
        self.assertEqual(0, self.report(job_id)["budget"]["reserved_tokens"])
        run = self.client.get(f"/api/runs/{job_id}").get_json()
        self.assertEqual("EXPLORE", run["result"]["solver"]["phase"])

    def test_expired_deadline_after_response_prevents_math_acceptance(self):
        original = SolverStateStore.commit_event

        def expire(store, *args, **kwargs):
            if kwargs["event"]["type"] == "solution_review_assessed":
                # Provider completed under the deadline; only the math commit
                # sees an expired clock, reproducing the post-Adapter window.
                with patch("showcase.solver_harness.product_control.time.time", return_value=time.time() + 60):
                    return original(store, *args, **kwargs)
            return original(store, *args, **kwargs)

        self.enterContext(patch.object(SolverStateStore, "commit_event", expire))
        self.open_star([SOLVED, POLISH, ACCEPT], SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_runtime_seconds=30))
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("failed", job["status"])
        self.assertEqual("run_deadline_exhausted", job["error"])
        run = self.client.get(f"/api/runs/{job_id}").get_json()
        self.assertNotEqual("completed_llm_reviewed", run["result"]["solver"]["status"])
        self.assertEqual(3, len(self.outbound))

    def test_cancel_after_verifier_response_prevents_math_acceptance(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original = SolverStateStore.commit_event

        def barrier(store, *args, **kwargs):
            if kwargs["event"]["type"] == "solution_review_assessed":
                entered.set()
                release.wait(5)
                try:
                    return original(store, *args, **kwargs)
                finally:
                    finished.set()
            return original(store, *args, **kwargs)

        self.enterContext(patch.object(SolverStateStore, "commit_event", barrier))
        self.open_star([SOLVED, POLISH, ACCEPT])
        job_id = self.create_job()
        self.assertTrue(entered.wait(5))
        self.cancel(job_id)
        release.set()
        self.assertTrue(finished.wait(5))
        self.assertEqual("canceled", self.job(job_id)["status"])
        run = self.client.get(f"/api/runs/{job_id}").get_json()
        self.assertNotEqual("completed_llm_reviewed", run["result"]["solver"]["status"])
        self.assertEqual(3, len(self.outbound))
        self.assertEqual(30, self.report(job_id)["budget"]["provider_known"]["total_tokens"])


if __name__ == "__main__":
    unittest.main()
