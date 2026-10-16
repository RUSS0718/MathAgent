"""Black-box contracts for the durable Job SSE stream."""

from __future__ import annotations

import re
import tempfile
import threading
import time
import unittest
from pathlib import Path

from showcase.flask_app import create_app


def parse_sse(body: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for block in re.split(r"\r?\n\r?\n", body.strip()):
        if not block or block.startswith(":"):
            continue
        fields: dict[str, str] = {}
        data: list[str] = []
        for line in block.splitlines():
            if line.startswith("data:"):
                data.append(line[5:].lstrip())
            elif ":" in line:
                key, value = line.split(":", 1)
                fields[key] = value.lstrip()
        events.append({"id": fields.get("id"), "event": fields.get("event"), "data": "\n".join(data)})
    return events


class SseContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "showcase-v0.2"
        self.app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": str(self.root)})
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
        self.headers = {"X-CSRF-Token": self.csrf, "Idempotency-Key": "sse-contract"}
        self.session_id = self.client.post("/api/new_chat", headers={"X-CSRF-Token": self.csrf}).get_json()["new_session_id"]

    def tearDown(self) -> None:
        self.app.extensions["showcase_workspace_service"].close()
        self.app.extensions["showcase_run_service"].close()
        self.app.extensions["loopback_store"].close()
        self.temp_dir.cleanup()

    def _create_job(self, *, key: str = "sse-contract") -> str:
        response = self.client.post(
            "/api/agent/jobs",
            json={"message": "求解 x + 1 = 2", "session_id": self.session_id},
            headers={"X-CSRF-Token": self.csrf, "Idempotency-Key": key},
        )
        self.assertEqual(202, response.status_code)
        return response.get_json()["job_id"]

    def test_stream_projects_durable_events_and_last_event_id(self) -> None:
        job_id = self._create_job()
        response = self.client.get(f"/api/agent/jobs/{job_id}/events")
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.content_type.startswith("text/event-stream"))
        events = parse_sse(response.get_data(as_text=True))
        self.assertGreaterEqual(len(events), 3)
        self.assertEqual(["queued", "running", "final_result"], [event["event"] for event in events[-3:]])
        ids = [int(event["id"]) for event in events if event["id"] is not None]
        self.assertEqual(ids, sorted(ids))
        self.assertTrue(all(value > 0 for value in ids))

        resumed = self.client.get(
            f"/api/agent/jobs/{job_id}/events?last_event_id={ids[0]}",
            headers={"Last-Event-ID": str(ids[0] - 1)},
        )
        resumed_events = parse_sse(resumed.get_data(as_text=True))
        self.assertEqual([ids[1], ids[2]], [int(event["id"]) for event in resumed_events])

    def test_bad_cursor_has_stable_error(self) -> None:
        job_id = self._create_job()
        for query, headers in (("-1", {}), ("abc", {}), (None, {"Last-Event-ID": "abc"})):
            path = f"/api/agent/jobs/{job_id}/events"
            if query is not None:
                path += f"?last_event_id={query}"
            response = self.client.get(path, headers=headers)
            self.assertEqual(400, response.status_code)
            self.assertEqual("invalid_last_event_id", response.get_json()["error"])

    def test_stream_sends_heartbeat_while_job_is_running(self) -> None:
        service = self.app.extensions["showcase_workspace_service"]
        blocked = threading.Event()
        release = threading.Event()

        def hold_job(job_id: str) -> None:
            blocked.set()
            release.wait(timeout=2)
            service.store.start_job(job_id)
            service.store.complete_job(job_id, "答案：1", "确定性测试")

        service._execute = hold_job
        job_id = self._create_job(key="heartbeat-contract")
        self.assertTrue(blocked.wait(timeout=1))
        response = self.client.get(f"/api/agent/jobs/{job_id}/events", buffered=False)
        first = next(response.response).decode("utf-8")
        self.assertIn("event: queued", first)
        heartbeat = next(response.response).decode("utf-8")
        self.assertIn("event: heartbeat", heartbeat)
        self.assertNotIn("id:", heartbeat)
        release.set()
        rest = b"".join(response.response).decode("utf-8")
        response.close()
        self.assertIn("event: final_result", rest)

    def test_events_do_not_cross_job_sessions(self) -> None:
        first_job = self._create_job(key="session-a")
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if self.client.get(f"/api/agent/jobs/{first_job}").get_json()["status"] == "succeeded":
                break
            time.sleep(0.01)
        second_session = self.client.post("/api/new_chat", headers={"X-CSRF-Token": self.csrf}).get_json()["new_session_id"]
        second = self.client.post(
            "/api/agent/jobs",
            json={"message": "题目 B", "session_id": second_session},
            headers={"X-CSRF-Token": self.csrf, "Idempotency-Key": "session-b"},
        )
        second_job = second.get_json()["job_id"]
        first_events = parse_sse(self.client.get(f"/api/agent/jobs/{first_job}/events").get_data(as_text=True))
        self.assertTrue(first_events)
        self.assertTrue(all(second_job not in str(event) for event in first_events))


if __name__ == "__main__":
    unittest.main()
