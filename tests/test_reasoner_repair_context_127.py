"""A serialization repair receives the actual failed text, rather than a blind retry."""

import unittest
from copy import deepcopy

from llm_client import InternChatClient
from showcase.adapters import InternStreamAdapter
from showcase.run_budget import RunBudgetLimits
from showcase.solver_harness.protocol_repair import repair_request
from tests.star_product_support import ACCEPT, RawProviderContent, StarJobFixture
from tests.test_star_product_challenge import CHALLENGE, FEATURES, STEP, STEP_ACCEPT
from tests.test_star_product_tools import NEED_PLAN, PLAN

BAD = ('{"argument":"proof","claims":[{"statement":"count","label":"easy-verify",'
       '"tool_request":{"tool":"python_math","arguments":{"code":"print(1)}, '
       '"scope":"finite_computation"}}],"blocked":false}')


class ReasonerRepairContextTest(StarJobFixture, unittest.TestCase):
    def test_unknown_or_unrelated_reply_never_enters_repair_context(self):
        request = {"run_id": "one", "call_id": "call", "role": "reasoner"}
        failed = {**request, "status": "protocol_failed", "error_category": "invalid_json",
                  "partial_text": BAD}
        before = deepcopy(failed)
        result = repair_request(request, failed_call=failed)
        self.assertEqual(BAD, result["format_repair"]["previous_response"])
        self.assertEqual(before, failed)
        for changed in ({"run_id": "other"}, {"call_id": "other"}, {"role": "meta"},
                        {"status": "unknown_outcome"}, {"error_category": "tls"}):
            with self.subTest(changed=changed):
                self.assertNotIn("format_repair", repair_request(request, failed_call={**failed, **changed}))

    def test_step_and_challenge_repair_include_exact_failed_reply_and_error(self):
        for challenge in (False, True):
            with self.subTest(challenge=challenge):
                replies = [NEED_PLAN, PLAN]
                if challenge:
                    replies += [STEP, CHALLENGE]
                replies += [RawProviderContent(BAD), STEP, STEP_ACCEPT,
                            {"final_response": "2"}, ACCEPT]
                self.open_star(replies, SHOWCASE_STAR_FEATURES=FEATURES,
                               SHOWCASE_STAR_ADAPTER=InternStreamAdapter(
                                   InternChatClient(retry=1), max_tokens=256),
                               SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                                   max_model_calls=12, max_http_attempts=12))
                job = self.terminal(self.create_job())
                self.assertEqual("succeeded", job["status"], job)
                request = next(r for r in self.outbound if r["call_id"].endswith(":repair-1"))
                repair = request.get("format_repair", {})
                self.assertEqual(BAD, repair.get("previous_response"))
                self.assertEqual("Expecting ',' delimiter", repair.get("json_error", {}).get("message"))
                self.assertIsInstance(repair["json_error"]["position"], int)
                self.assertEqual(1, sum(r["call_id"].endswith(":repair-1") for r in self.outbound))
                self.assertEqual("same_artifact", job["result"]["solver"]["semantics"]["binding"])
