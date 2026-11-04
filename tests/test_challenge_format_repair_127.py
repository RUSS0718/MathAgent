"""Challenge replies receive the same bounded format repair as initial steps."""

import unittest

import requests

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, RawProviderContent, StarJobFixture
from tests.test_star_product_challenge import CHALLENGE, STEP_ACCEPT
from tests.test_star_product_planning import FEATURES, STEP
from tests.test_star_product_tools import NEED_PLAN, PLAN


class ChallengeFormatRepairTest(StarJobFixture, unittest.TestCase):
    def run_failure(self, failure, continuation):
        self.open_star([NEED_PLAN, PLAN, STEP, CHALLENGE, failure, *continuation],
                       SHOWCASE_STAR_FEATURES=FEATURES,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=12, max_http_attempts=12))
        job_id = self.create_job()
        return self.terminal(job_id)

    def test_complete_malformed_challenge_repairs_once_and_delivers(self):
        job = self.run_failure(RawProviderContent('{"argument":"proof"'),
                               [STEP, STEP_ACCEPT, {"final_response": "2"}, ACCEPT])
        self.assertEqual("succeeded", job["status"])
        challenged = [r for r in self.outbound if r["role"] == "reasoner" and r.get("round")]
        self.assertEqual(2, len(challenged))
        self.assertTrue(challenged[1]["call_id"].endswith(":repair-1"))
        self.assertEqual(challenged[0]["objection"], challenged[1]["objection"])
        self.assertEqual("same_artifact", job["result"]["solver"]["semantics"]["binding"])
        self.assertEqual(9, job["result"]["budget"]["http_attempts"])

    def test_second_malformed_reply_stops_without_a_third_attempt(self):
        job = self.run_failure(RawProviderContent("broken"), [RawProviderContent("still broken")])
        self.assertEqual("failed", job["status"])
        self.assertEqual(6, len(self.outbound))
        self.assertEqual("protocol_failure_unrepaired", job["error"])

    def test_unknown_transport_does_not_repair_or_resend(self):
        job = self.run_failure(requests.ReadTimeout("unknown outcome"), [])
        self.assertEqual("failed", job["status"])
        self.assertEqual(5, len(self.outbound))
        self.assertFalse(any(r.get("repair_instruction") for r in self.outbound))
        self.assertEqual(1, job["result"]["budget"]["unresolved_attempts"])


if __name__ == "__main__":
    unittest.main()
