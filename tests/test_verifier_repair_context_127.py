"""Existing Verifier repairs receive the failed text on each owned review path."""

import unittest

from llm_client import InternChatClient
from showcase.adapters import InternStreamAdapter
from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, POLISH, SOLVED, RawProviderContent, StarJobFixture
from tests.test_star_product_challenge import FEATURES, STEP, STEP_ACCEPT
from tests.test_star_product_tools import NEED_PLAN, PLAN

BAD = '{"verdict":"ACCEPT" "objection":"format test"}'


class VerifierRepairContextTest(StarJobFixture, unittest.TestCase):
    def test_step_and_both_whole_review_paths_receive_exact_failure(self):
        cases = {
            "step": [NEED_PLAN, PLAN, STEP, RawProviderContent(BAD), STEP_ACCEPT,
                     {"final_response": "2"}, ACCEPT],
            "plan-whole": [NEED_PLAN, PLAN, STEP, STEP_ACCEPT,
                           {"final_response": "2"}, RawProviderContent(BAD), ACCEPT],
            "fast-whole": [SOLVED, POLISH, RawProviderContent(BAD), ACCEPT],
        }
        for name, replies in cases.items():
            with self.subTest(path=name):
                self.open_star(replies, SHOWCASE_STAR_FEATURES=FEATURES,
                               SHOWCASE_STAR_ADAPTER=InternStreamAdapter(
                                   InternChatClient(retry=1), max_tokens=256),
                               SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                                   max_model_calls=12, max_http_attempts=12))
                job = self.terminal(self.create_job())
                self.assertEqual("succeeded", job["status"], job)
                repairs = [r for r in self.outbound if r["call_id"].endswith(":repair-1")]
                self.assertEqual(1, len(repairs))
                self.assertEqual(BAD, repairs[0].get("format_repair", {}).get("previous_response"))
                self.assertEqual("Expecting ',' delimiter", repairs[0]["format_repair"]["json_error"]["message"])
                self.assertFalse(repairs[0]["call_id"].endswith(":repair-1:repair-1"))
                self.assertEqual("same_artifact", job["result"]["solver"]["semantics"]["binding"])
