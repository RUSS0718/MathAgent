"""Black-box contracts for the v0.2 ChatSession and Job workspace."""

from __future__ import annotations

import tempfile
import time
import unittest
import uuid
from pathlib import Path

from showcase.flask_app import create_app


class WorkspaceJobsContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "showcase-v0.2"
        self.app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": str(self.root)})
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]

    def tearDown(self) -> None:
        self.app.extensions["showcase_workspace_service"].close()
        self.app.extensions["showcase_run_service"].close()
        self.app.extensions["loopback_store"].close()
        self.temp_dir.cleanup()

    def _headers(self, **extra: str) -> dict[str, str]:
        headers = {"X-CSRF-Token": self.csrf}
        headers.update(extra)
        return headers

    def test_session_lifecycle_uses_causal_compatible_shapes(self) -> None:
        listed = self.client.get("/api/sessions")
        self.assertEqual(200, listed.status_code)
        self.assertEqual([], listed.get_json())

        created = self.client.post("/api/new_chat", headers=self._headers())
        self.assertEqual(200, created.status_code)
        session_id = created.get_json()["new_session_id"]

        renamed = self.client.post(
            "/api/change_session",
            json={"session_id": session_id, "title": "二次方程"},
            headers=self._headers(),
        )
        self.assertEqual({"success": True, "session_id": session_id, "title": "二次方程"}, renamed.get_json())

        loaded = self.client.get(f"/api/load_session?session={session_id}")
        self.assertEqual({"success": True, "messages": []}, loaded.get_json())
        self.assertEqual(session_id, self.client.get("/api/sessions").get_json()[0][0])

        deleted = self.client.post(
            "/api/delete_session",
            json={"session_id": session_id},
            headers=self._headers(),
        )
        self.assertEqual({"success": True}, deleted.get_json())
        self.assertEqual([], self.client.get("/api/sessions").get_json())

    def test_job_is_accepted_before_fake_adapter_finishes_and_history_is_unique(self) -> None:
        session_id = self.client.post("/api/new_chat", headers=self._headers()).get_json()["new_session_id"]
        first_key = str(uuid.uuid4())
        response = self.client.post(
            "/api/agent/jobs",
            json={"message": "计算 1 + 1", "session_id": session_id, "web_search_enabled": False},
            headers=self._headers(**{"Idempotency-Key": first_key}),
        )

        self.assertEqual(202, response.status_code)
        body = response.get_json()
        self.assertEqual({"success": True, "status": "queued", "existing": False}, {k: body[k] for k in ("success", "status", "existing")})
        self.assertTrue(body["job_id"])

        deadline = time.monotonic() + 2
        messages: list[dict[str, object]] = []
        while time.monotonic() < deadline:
            messages = self.client.get(f"/api/load_session?session={session_id}").get_json()["messages"]
            if len(messages) == 2:
                break
            time.sleep(0.01)
        self.assertEqual(2, len(messages))
        self.assertEqual(["user", "ai"], [message["sender"] for message in messages])
        self.assertEqual(body["job_id"], messages[0]["analysis_job_id"])
        self.assertEqual(body["job_id"], messages[1]["analysis_job_id"])

        replay = self.client.post(
            "/api/agent/jobs",
            json={"message": "计算 1 + 1", "session_id": session_id, "web_search_enabled": False},
            headers=self._headers(**{"Idempotency-Key": first_key}),
        )
        self.assertEqual(200, replay.status_code)
        self.assertEqual({"success": True, "job_id": body["job_id"], "existing": True}, {
            "success": replay.get_json()["success"],
            "job_id": replay.get_json()["job_id"],
            "existing": replay.get_json()["existing"],
        })
        self.assertEqual(2, len(self.client.get(f"/api/load_session?session={session_id}").get_json()["messages"]))

    def test_one_active_job_per_session_and_capability_errors_are_stable(self) -> None:
        session_id = self.client.post("/api/new_chat", headers=self._headers()).get_json()["new_session_id"]
        first = self.client.post(
            "/api/agent/jobs",
            json={"message": "题目 A", "session_id": session_id},
            headers=self._headers(**{"Idempotency-Key": str(uuid.uuid4())}),
        )
        self.assertEqual(202, first.status_code)

        second = self.client.post(
            "/api/agent/jobs",
            json={"message": "题目 B", "session_id": session_id},
            headers=self._headers(**{"Idempotency-Key": str(uuid.uuid4())}),
        )
        self.assertEqual(409, second.status_code)
        self.assertEqual("active_job_conflict", second.get_json()["code"])
        self.assertTrue(second.headers.get("X-Request-ID"))

        unavailable = self.client.post(
            "/api/agent/jobs",
            json={"message": "上传题", "session_id": session_id, "input_user_file_id": 1},
            headers=self._headers(**{"Idempotency-Key": str(uuid.uuid4())}),
        )
        self.assertEqual(503, unavailable.status_code)
        self.assertEqual("capability_unavailable", unavailable.get_json()["code"])


if __name__ == "__main__":
    unittest.main()
