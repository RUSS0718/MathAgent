from __future__ import annotations

import tempfile
import time
import unittest
import uuid
from pathlib import Path

from showcase.flask_app import create_app


class JobControlContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "showcase"
        self.app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": str(self.root), "SHOWCASE_JOB_DELAY_SECONDS": 0.2, "SHOWCASE_WAITING_INPUT_MARKER": "等待输入:"})
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
        self.session_id = self.client.post("/api/new_chat", headers=self._headers()).get_json()["new_session_id"]

    def tearDown(self) -> None:
        self.app.extensions["showcase_workspace_service"].close()
        self.app.extensions["showcase_run_service"].close()
        self.app.extensions["loopback_store"].close()
        self.temp_dir.cleanup()

    def _headers(self, **extra: str) -> dict[str, str]:
        headers = {"X-CSRF-Token": self.csrf}
        headers.update(extra)
        return headers

    def test_create_requires_uuid_v4_idempotency_key(self) -> None:
        response = self.client.post(
            "/api/agent/jobs",
            json={"message": "题目", "session_id": self.session_id},
            headers=self._headers(**{"Idempotency-Key": "job-key"}),
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual("idempotency_key_invalid", response.get_json()["code"])

    def test_cancel_is_idempotent_and_late_completion_cannot_reopen(self) -> None:
        key = str(uuid.uuid4())
        created = self.client.post(
            "/api/agent/jobs",
            json={"message": "题目", "session_id": self.session_id},
            headers=self._headers(**{"Idempotency-Key": key}),
        )
        self.assertEqual(202, created.status_code)
        job_id = created.get_json()["job_id"]
        cancel_key = str(uuid.uuid4())
        canceled = self.client.post(
            f"/api/agent/jobs/{job_id}/cancel",
            json={},
            headers=self._headers(**{"Idempotency-Key": cancel_key}),
        )
        self.assertEqual(200, canceled.status_code)
        self.assertEqual("canceled", canceled.get_json()["status"])
        replay = self.client.post(
            f"/api/agent/jobs/{job_id}/cancel",
            json={},
            headers=self._headers(**{"Idempotency-Key": cancel_key}),
        )
        self.assertEqual(200, replay.status_code)
        self.assertTrue(replay.get_json()["existing"])
        time.sleep(0.25)
        self.assertEqual("canceled", self.client.get(f"/api/agent/jobs/{job_id}").get_json()["status"])
        events = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        self.assertIn("event: canceled", events)

    def test_resume_waiting_input_records_resumed_event(self) -> None:
        created = self.client.post(
            "/api/agent/jobs",
            json={"message": "等待输入:题目", "session_id": self.session_id},
            headers=self._headers(**{"Idempotency-Key": str(uuid.uuid4())}),
        )
        job_id = created.get_json()["job_id"]
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            if self.client.get(f"/api/agent/jobs/{job_id}").get_json()["status"] == "waiting_input":
                break
            time.sleep(0.01)
        response = self.client.post(
            f"/api/agent/jobs/{job_id}/resume",
            json={"answer": "补充条件"},
            headers=self._headers(**{"Idempotency-Key": str(uuid.uuid4())}),
        )
        self.assertEqual(202, response.status_code)
        self.assertEqual("queued", response.get_json()["status"])
        self.assertIn("event: resumed", self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True))

    def test_recovery_marks_incomplete_job_for_review(self) -> None:
        paused = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": str(self.root), "SHOWCASE_WORKER_ENABLED": False})
        paused_client = paused.test_client()
        paused_csrf = paused_client.get("/api/check_auth").get_json()["csrf_token"]
        paused_session = paused_client.post("/api/new_chat", headers={"X-CSRF-Token": paused_csrf}).get_json()["new_session_id"]
        created = paused_client.post(
            "/api/agent/jobs",
            json={"message": "题目", "session_id": paused_session},
            headers={"X-CSRF-Token": paused_csrf, "Idempotency-Key": str(uuid.uuid4())},
        ).get_json()
        paused.extensions["showcase_workspace_service"].close()
        paused.extensions["showcase_run_service"].close()
        paused.extensions["loopback_store"].close()
        recovered = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": str(self.root)})
        recovered_client = recovered.test_client()
        recovered_client.get("/api/check_auth")
        body = recovered_client.get(f"/api/agent/jobs/{created['job_id']}").get_json()
        self.assertEqual("failed", body["status"])
        recovered.extensions["showcase_workspace_service"].close()
        recovered.extensions["showcase_run_service"].close()
        recovered.extensions["loopback_store"].close()


if __name__ == "__main__":
    unittest.main()
