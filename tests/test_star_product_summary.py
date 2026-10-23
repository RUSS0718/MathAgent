"""Public persisted progress summary for the workbench."""
import unittest

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_star_product_planning import FEATURES, STEP
from tests.test_star_product_tools import NEED_PLAN, PLAN, VERDICT


class StarSummaryTest(StarJobFixture, unittest.TestCase):
    def test_report_has_persisted_plan_and_gate_without_private_proof(self):
        self.open_star([NEED_PLAN, PLAN, STEP, VERDICT, {'final_response': '2'}, ACCEPT],
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=12, max_http_attempts=12))
        run_id = self.create_job()
        self.terminal(run_id)
        solver = self.report(run_id)['solver']['solver']
        self.assertEqual(1, solver['progress']['plan_version'])
        self.assertEqual('ACCEPT', solver['progress']['steps'][0]['verdict'])
        self.assertEqual('步骤 1', solver['progress']['steps'][0]['label'])
        self.assertNotIn('Addition gives two', str(solver['progress']))
