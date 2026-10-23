"""Cancellation at the mathematical commit boundary of actual public STAR Jobs."""

import threading
import unittest
from unittest.mock import patch

from showcase.solver_harness.storage import SolverStateStore
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture


class StarControlTest(StarJobFixture, unittest.TestCase):
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
