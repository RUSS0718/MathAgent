import unittest

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import StarJobFixture
from tests.test_faithful_s03_job import FEATURES, REPLIES, SPEC


class FaithfulS08PublicJobTest(StarJobFixture, unittest.TestCase):
    def test_serial_route_is_persisted_and_projected_without_private_frontier(self):
        self.open_star(
            REPLIES,
            SHOWCASE_STAR_FEATURES={**FEATURES, "context_pack": False, "serial_routes": True},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8),
        )
        created = self.client.post(
            "/api/agent/jobs",
            json={"message": SPEC["original_problem"], "session_id": self.session,
                  "solver_mode": "star_limited", "problem_spec": SPEC},
            headers=self.headers(),
        )
        self.assertEqual(202, created.status_code, created.get_json())
        job_id = created.get_json()["job_id"]
        terminal = self.terminal(job_id)
        self.assertEqual("succeeded", terminal["status"], terminal)
        report = self.report(job_id)
        routes = report["solver"]["solver"]["progress"]["routes"]
        self.assertEqual("serial-aprs-v1", routes["policy_version"])
        self.assertEqual(1, len(routes["items"]))
        self.assertEqual("primary", routes["items"][0]["kind"])
        self.assertEqual("active", routes["items"][0]["status"])
        self.assertTrue(routes["decisions"][-1]["replayable"])
        encoded = repr(report)
        self.assertNotIn(SPEC["root_obligations"][0]["statement"], encoded)
        self.assertNotIn("prove-value", encoded)
