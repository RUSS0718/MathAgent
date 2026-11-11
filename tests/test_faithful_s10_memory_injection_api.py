import sqlite3
import unittest
import uuid
from contextlib import closing

from showcase.solver_harness.faithful_memory import FaithfulMemoryStore, MemoryScope
from tests.star_product_support import StarJobFixture


class PopulationMemoryInjectionAPITest(StarJobFixture, unittest.TestCase):
    def test_injection_requires_explicit_session_enablement(self):
        self.open_star([], SHOWCASE_FAITHFUL_MEMORY_ENABLED=True)
        url = f"/api/sessions/{self.session}/memory/population/{self.session}"
        injection_url = url + "/injection"
        workspace = self.app.extensions["showcase_workspace_service"].store
        job, _ = workspace.create_job(
            user_id="local-user", session_id=self.session, problem="test",
            idempotency_key=uuid.uuid4().hex, request_digest=uuid.uuid4().hex,
        )
        scope = MemoryScope("population", self.session, "local-user", self.session)
        with closing(sqlite3.connect(self.app.config["SHOWCASE_DATABASE_PATH"])) as connection:
            store = FaithfulMemoryStore(connection)
            record_id = store.record_observation(
                scope,
                {
                    "outcome": "failure",
                    "applicability": {"domain": "algebra"},
                    "versions": {}, "cost": {}, "content": {},
                },
                provenance={"source_run_id": job["job_id"]},
            )

        initial = self.client.get(url)
        self.assertEqual(200, initial.status_code, initial.get_json())
        self.assertIs(initial.get_json()["injection_enabled"], False)

        enabled = self.client.put(injection_url, json={"enabled": True}, headers=self.headers())
        self.assertEqual(200, enabled.status_code, enabled.get_json())
        self.assertIs(enabled.get_json()["injection_enabled"], True)
        self.assertIs(self.client.get(url).get_json()["injection_enabled"], True)

        disabled = self.client.put(injection_url, json={"enabled": False}, headers=self.headers())
        self.assertEqual(200, disabled.status_code, disabled.get_json())
        self.assertIs(disabled.get_json()["injection_enabled"], False)
        self.assertIs(self.client.get(url).get_json()["injection_enabled"], False)

        # Injection consent is independent from visibility and observation writes.
        visible = self.client.get(url)
        self.assertEqual(200, visible.status_code)
        self.assertEqual([record_id], [item["record_id"] for item in visible.get_json()["observations"]])


if __name__ == "__main__":
    unittest.main()
