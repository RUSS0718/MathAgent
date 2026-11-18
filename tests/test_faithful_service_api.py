"""Public admission for the opt-in autonomous service, with no provider dispatch."""

import tempfile
import unittest
import uuid
from unittest.mock import patch

from showcase.flask_app import create_app
from tests.test_faithful_s03_job import CAPACITY_POLICY, FEATURES


class FaithfulServiceApiTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.app = create_app({
            "TESTING": True, "SHOWCASE_DATA_DIR": temp.name,
            "SHOWCASE_WORKER_ENABLED": False,
            "SHOWCASE_STAR_FULL_ENABLED": True,
            "SHOWCASE_FAITHFUL_AUTONOMOUS": True,
            "SHOWCASE_STAR_FULL_FEATURES": {**FEATURES, "auto_problem_spec": True},
            "SHOWCASE_STAR_CONTEXT_CAPACITY": CAPACITY_POLICY,
        })
        for key in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            self.addCleanup(self.app.extensions[key].close)
        self.pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        self.client = self.app.test_client()
        csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
        self.headers = {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}
        self.session = self.client.post("/api/new_chat", headers=self.headers).get_json()["new_session_id"]

    def test_unavailable_service_advertises_reason_instead_of_legacy(self):
        faithful = self.client.get("/api/capabilities").get_json()["faithful"]
        self.assertTrue(faithful["enabled"])
        self.assertFalse(faithful["ready"])
        self.assertTrue(faithful["unavailable_reasons"])
        self.assertEqual("star_reference", faithful["solver_mode"])
        self.assertEqual("automatic", faithful["input_mode"])
        self.assertEqual("faithful-capabilities-v1", faithful["version"])
        self.assertEqual("experimental", faithful["maturity"])
        self.assertTrue(faithful["features"]["auto_problem_spec"])
        self.assertIn("formal_not_configured", faithful["optional_limitations"])

    def test_plain_text_is_admitted_idempotently_without_fabricated_spec(self):
        with patch.object(self.pipeline, "full_gaps", return_value=[]):
            payload = {"message": "1+1", "session_id": self.session}
            first = self.client.post("/api/agent/jobs", json=payload, headers=self.headers)
            self.assertEqual(202, first.status_code, first.get_json())
            again = self.client.post("/api/agent/jobs", json=payload, headers=self.headers)
            self.assertEqual(first.get_json()["job_id"], again.get_json()["job_id"])
        workspace = self.app.extensions["showcase_workspace_service"]
        job_id = first.get_json()["job_id"]
        self.assertEqual("star_reference", workspace.store.job_identity(job_id)["solver_mode"])
        self.assertIsNone(workspace.store.problem_spec(job_id))

    def test_unavailable_mode_cannot_fall_back_to_legacy(self):
        response = self.client.post("/api/agent/jobs", headers=self.headers,
                                    json={"message": "1+1", "session_id": self.session})
        self.assertEqual(503, response.status_code)

    def test_waiting_checkpoint_advertises_actual_resume_admission(self):
        with patch.object(self.pipeline, "full_gaps", return_value=[]):
            created = self.client.post("/api/agent/jobs", headers=self.headers,
                json={"message": "1+1", "session_id": self.session})
        self.assertEqual(202, created.status_code)
        job_id = created.get_json()["job_id"]
        store = self.app.extensions["showcase_workspace_service"].store
        store.mark_waiting_input(job_id)
        job = self.client.get(f"/api/agent/jobs/{job_id}").get_json()
        self.assertEqual(["cancel", "resume"], job["result"]["faithful"]["allowed_actions"])
        from showcase.faithful_intervention_control import ensure_control_schema

        # A real intervention owner must block both the read projection and POST.
        with store._lock:
            ensure_control_schema(store._connection)
            store._connection.execute(
                "INSERT INTO faithful_intervention_control(job_id,run_id,status,updated_at) VALUES(?,?,'paused',0)",
                (job_id, job_id))
            store._connection.commit()
        guarded = self.client.get(f"/api/agent/jobs/{job_id}").get_json()
        self.assertEqual(["cancel"], guarded["result"]["faithful"]["allowed_actions"])
        refused = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={},
            headers={**self.headers, "Idempotency-Key": str(uuid.uuid4())})
        self.assertEqual(409, refused.status_code, refused.get_json())
        with store._lock:
            store._connection.execute("DELETE FROM faithful_intervention_control WHERE job_id=?", (job_id,))
            store._connection.execute("UPDATE run_budgets SET ledger_json=json_set(ledger_json, '$.deadline_at', 0) WHERE run_id=?", (job_id,))
            store._connection.commit()
        # Existing waiting_input control accepts queueing even after expiry;
        # runtime dispatch still observes the unchanged root deadline.
        expired = self.client.get(f"/api/agent/jobs/{job_id}").get_json()
        self.assertEqual(["cancel", "resume"], expired["result"]["faithful"]["allowed_actions"])
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={},
            headers={**self.headers, "Idempotency-Key": str(uuid.uuid4())})
        self.assertEqual(202, response.status_code, response.get_json())
