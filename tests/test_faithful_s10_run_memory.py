"""S10 Run Memory is a scoped view of the authoritative persisted Job state."""

import unittest

from showcase.faithful_memory_api import project_run_memory
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture


class FaithfulS10RunMemoryTest(StarJobFixture, unittest.TestCase):
    def test_conjecture_and_invalidated_result_are_not_effective_evidence(self):
        state = {
            "verified_results_ledger": [
                {
                    "result_id": "a",
                    "proven": True,
                    "valid": True,
                    "evidence_level": "llm_reviewed",
                    "category": "Lemma",
                },
                {
                    "result_id": "b",
                    "proven": False,
                    "valid": True,
                    "evidence_level": "conjecture",
                    "category": "Conjecture",
                },
                {
                    "result_id": "c",
                    "proven": True,
                    "valid": False,
                    "evidence_level": "tool_verified",
                    "category": "Computation",
                },
            ]
        }
        memory = project_run_memory("run-1", 4, state)
        self.assertEqual(["a"], [item["result_id"] for item in memory["valid_evidence"]])
        self.assertEqual("llm_reviewed", memory["valid_evidence"][0]["evidence_level"])
        self.assertEqual(1, memory["invalidated_count"])

    def test_public_memory_uses_persisted_run_without_promoting_evidence(self):
        self.open_star([SOLVED, POLISH, ACCEPT], SHOWCASE_FAITHFUL_MEMORY_ENABLED=True)
        created = self.client.post(
            "/api/agent/jobs",
            json={
                "message": "Compute 1+1",
                "session_id": self.session,
                "solver_mode": "star_limited",
            },
            headers=self.headers(),
        )
        self.assertEqual(202, created.status_code, created.get_json())
        job_id = created.get_json()["job_id"]
        self.terminal(job_id)

        response = self.client.get(f"/api/agent/jobs/{job_id}/memory")
        self.assertEqual(200, response.status_code, response.get_json())
        memory = response.get_json()["run_memory"]
        self.assertEqual(job_id, memory["run_id"])
        self.assertIsInstance(memory["state_revision"], int)
        self.assertEqual("authoritative_run_snapshot", memory["source"])
        job = self.client.get(f"/api/agent/jobs/{job_id}").get_json()
        self.assertEqual(job["result"]["budget"], memory["budget"])
        self.assertIn("valid_evidence", memory)
        self.assertNotIn("problem", memory)
        self.assertNotIn("prompt_layers", memory)
        outbound_count = len(self.outbound)
        self.assertEqual(
            memory, self.client.get(f"/api/agent/jobs/{job_id}/memory").get_json()["run_memory"]
        )
        self.assertEqual(outbound_count, len(self.outbound))
        anonymous = self.app.test_client()
        self.assertEqual(401, anonymous.get(f"/api/agent/jobs/{job_id}/memory").status_code)

    def test_memory_endpoint_is_disabled_by_default(self):
        self.open_star([SOLVED, POLISH, ACCEPT])
        response = self.client.get("/api/agent/jobs/any/memory")
        self.assertEqual(404, response.status_code)
