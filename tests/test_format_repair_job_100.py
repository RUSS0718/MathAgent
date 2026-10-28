"""F05/F06/F08/F10 through authenticated Jobs with finite offline HTTP replies."""

import json
import unittest

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, POLISH, SOLVED, RawProviderContent, StarJobFixture


class FormatRepairJobTest(StarJobFixture, unittest.TestCase):
    def open_repair(self, replies, **config):
        self.open_star(replies, SHOWCASE_STAR_FEATURES={"serialization_repair": True},
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=12,
                           max_http_attempts=12), **config)
        return self.create_job()

    def test_f05_job_repairs_same_values_as_new_call_on_original_run_budget(self):
        raw = "```json\n" + json.dumps(SOLVED) + "\n```"
        job_id = self.open_repair([RawProviderContent(raw), SOLVED, POLISH, ACCEPT])
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        budget = job["result"]["budget"]
        self.assertEqual(4, budget["logical_calls"])
        self.assertEqual(4, budget["http_attempts"])
        self.assertEqual(40, budget["provider_known"]["total_tokens"])
        self.assertEqual(0, budget["unknown_attempts"])
        repair = self.outbound[1]
        self.assertEqual(raw, repair["visible_reply"])
        self.assertEqual([], repair["allowed_tools"])
        self.assertNotIn("original_problem", repair)
        self.assertNotIn("session_history", repair)
        public = json.dumps([job, self.report(job_id), self.client.get(
            f"/api/runs/{job_id}/evidence").get_json()])
        self.assertNotIn("visible_reply", public)
        self.assertNotIn("```", public)


if __name__ == "__main__":
    unittest.main()
