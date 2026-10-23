"""STAR resource admission observed through real Job and Adapter boundaries."""

import unittest

import requests

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture


class StarBudgetTest(StarJobFixture, unittest.TestCase):
    def test_retry_is_one_logical_call_and_preserves_unknown_attempt(self):
        self.open_star([requests.Timeout(), SOLVED, POLISH, ACCEPT], retry=2,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=3, max_http_attempts=4))
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        budget = self.report(job_id)["budget"]
        self.assertEqual(4, len(self.outbound))
        self.assertEqual(3, budget["logical_calls"])
        self.assertEqual(4, budget["http_attempts"])
        self.assertEqual(1, budget["unresolved_attempts"])
        self.assertGreater(budget["reserved_tokens"], 0)
        self.assertEqual(30, budget["provider_known"]["total_tokens"])


if __name__ == "__main__":
    unittest.main()
