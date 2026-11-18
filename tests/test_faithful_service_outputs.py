"""On-demand output and read-only restoration over an ordinary Faithful Job."""

import os
import unittest
from unittest.mock import patch

from showcase.run_budget import RunBudgetLimits
from showcase.star_product_config import CORE_FEATURES
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture
from tests.test_faithful_s03_job import CAPACITY_POLICY, ENDPOINT, SPEC


class FaithfulOutputsTest(StarJobFixture, unittest.TestCase):
    def test_plain_answer_explicit_outputs_restore_without_generation(self):
        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        self.open_star([SPEC, SOLVED, POLISH, ACCEPT],
            SHOWCASE_FAITHFUL_AUTONOMOUS=True, SHOWCASE_STAR_FULL_ENABLED=True,
            SHOWCASE_PRESENTATION_ENABLED=True,
            SHOWCASE_STAR_FULL_FEATURES=dict.fromkeys(CORE_FEATURES | {
                "auto_problem_spec", "problem_spec", "context_pack", "proof_graph",
                "progress_scheduling", "serial_routes"}, True),
            SHOWCASE_STAR_CONTEXT_CAPACITY=CAPACITY_POLICY,
            SHOWCASE_STAR_FULL_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8))
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        self.enterContext(patch.object(pipeline, "full_gaps", return_value=[]))
        created = self.client.post("/api/agent/jobs", headers=self.headers(),
            json={"message": "1+1", "session_id": self.session})
        self.assertEqual(202, created.status_code, created.get_json())
        job_id = created.get_json()["job_id"]
        before = self.terminal(job_id)
        self.assertEqual("succeeded", before["status"], before)
        calls = len(self.outbound)
        failed = self.client.post(f"/api/agent/jobs/{job_id}/teach",
            json={"renderer": "fail"}, headers=self.headers())
        self.assertEqual(200, failed.status_code, failed.get_json())
        self.assertEqual("failed", failed.get_json()["presentation"]["status"])
        self.assertEqual(before["result"]["final_response"], failed.get_json()["answer"])
        for mode in ("teach", "report"):
            path = f"/api/agent/jobs/{job_id}/outputs/{mode}"
            missing = self.client.get(path)
            self.assertEqual(404, missing.status_code)
            self.assertEqual("presentation_unavailable", missing.get_json()["code"])
            generated = self.client.post(f"/api/agent/jobs/{job_id}/{mode}",
                json={}, headers=self.headers())
            self.assertEqual(200, generated.status_code, generated.get_json())
            artifact = generated.get_json()["presentation"]
            self.assertEqual(before["result"]["final_response"], artifact["answer"])
            with patch("showcase.presentation_api.build_presentation", side_effect=AssertionError("GET generated")):
                for _ in range(2):
                    restored = self.client.get(path)
                    self.assertEqual(200, restored.status_code, restored.get_json())
                    self.assertEqual("no-store", restored.headers["Cache-Control"])
                    self.assertEqual(artifact, restored.get_json()["presentation"])
            self.assertEqual(calls, len(self.outbound))
        after = self.job(job_id)
        self.assertEqual(before["result"]["final_response"], after["result"]["final_response"])
        self.assertEqual(before["result"]["budget"], after["result"]["budget"])
