from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from showcase.experiment_job_adapter import PublicExperimentJobAdapter
from showcase.flask_app import create_app


class ExperimentJobEventPaginationTest(unittest.TestCase):
    def test_snapshot_projects_only_safe_stream_timing_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            app = create_app(
                {
                    "TESTING": True,
                    "SHOWCASE_DATA_DIR": str(Path(temporary) / "showcase"),
                    "SHOWCASE_WORKER_ENABLED": False,
                }
            )
            try:
                client = app.test_client()
                csrf = client.get("/api/check_auth").get_json()["csrf_token"]
                session_id = client.post(
                    "/api/new_chat", headers={"X-CSRF-Token": csrf}
                ).get_json()["new_session_id"]
                created = client.post(
                    "/api/agent/jobs",
                    json={"session_id": session_id, "message": "safe sample"},
                    headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())},
                )
                job_id = created.get_json()["job_id"]
                app.extensions["showcase_workspace_service"].store.append_event(
                    job_id,
                    {
                        "type": "solver_progress",
                        "solver_event_id": "solver_event_safe",
                        "solver": {},
                        "stream_activity": {
                            "first_content_at": "2026-11-03T00:00:01Z",
                            "last_content_at": "2026-11-03T00:00:09Z",
                            "status": "streaming",
                            "content_bytes": 42,
                            "text": "private answer fragment",
                            "unexpected": "must not escape",
                        },
                    },
                )

                response = client.get(
                    f"/api/agent/jobs/{job_id}/events?snapshot=1&last_event_id=0"
                )

                self.assertEqual(200, response.status_code)
                event = next(
                    item for item in response.get_json()["events"]
                    if item["event"] == "solver_progress"
                )
                self.assertEqual(
                    {
                        "first_content_at": "2026-11-03T00:00:01Z",
                        "last_content_at": "2026-11-03T00:00:09Z",
                        "status": "streaming",
                        "content_bytes": 42,
                    },
                    event.get("stream_activity"),
                    msg=response.get_json(),
                )
                self.assertNotIn("private answer fragment", response.get_data(as_text=True))
                self.assertNotIn("unexpected", response.get_data(as_text=True))
            finally:
                app.extensions["showcase_workspace_service"].close()
                app.extensions["showcase_run_service"].close()
                app.extensions["loopback_store"].close()

    def test_adapter_continues_after_page_with_no_public_events(self):
        class SnapshotClient:
            def __init__(self):
                self.paths = []

            def bootstrap(self):
                return {}

            def request(self, method, path):
                self.paths.append(path)
                if "last_event_id=0" in path:
                    return {"events": [], "next_cursor": 50, "has_more": True}
                return {
                    "events": [{"id": 51, "event": "queued", "summary": "Job queued"}],
                    "next_cursor": 51,
                    "has_more": False,
                }

        client = SnapshotClient()
        adapter = PublicExperimentJobAdapter(
            client,
            {},
            object(),
            object(),
            object(),
        )

        events = adapter.execution_events("job-01")

        self.assertEqual([51], [event["id"] for event in events])
        self.assertEqual(2, len(client.paths))
        self.assertIn("last_event_id=50", client.paths[1])

    def test_snapshot_finds_public_event_after_filtered_internal_events(self):
        """The event limit applies to public summaries, not raw event rows."""
        with tempfile.TemporaryDirectory() as temporary:
            app = create_app(
                {
                    "TESTING": True,
                    "SHOWCASE_DATA_DIR": str(Path(temporary) / "showcase"),
                    "SHOWCASE_WORKER_ENABLED": False,
                    "SHOWCASE_EXPERIMENT_IDEMPOTENCY_LOOKUP_ENABLED": True,
                }
            )
            try:
                client = app.test_client()
                csrf = client.get("/api/check_auth").get_json()["csrf_token"]
                session_id = client.post(
                    "/api/new_chat", headers={"X-CSRF-Token": csrf}
                ).get_json()["new_session_id"]
                created = client.post(
                    "/api/agent/jobs",
                    json={"session_id": session_id, "message": "safe sample"},
                    headers={
                        "X-CSRF-Token": csrf,
                        "Idempotency-Key": str(uuid.uuid4()),
                    },
                )
                self.assertIn(created.status_code, (200, 202))
                job_id = created.get_json()["job_id"]
                store = app.extensions["showcase_workspace_service"].store
                for index in range(50):
                    store.append_event(
                        job_id,
                        {"type": "internal_progress", "message": f"private-{index}"},
                    )
                store.append_event(job_id, {"type": "queued"})

                first_page = client.get(
                    f"/api/agent/jobs/{job_id}/events?snapshot=1&last_event_id=1&limit=50"
                )
                self.assertEqual(200, first_page.status_code)
                self.assertEqual([], first_page.get_json()["events"])
                self.assertEqual(51, first_page.get_json()["next_cursor"])
                self.assertTrue(first_page.get_json()["has_more"])

                second_page = client.get(
                    f"/api/agent/jobs/{job_id}/events?snapshot=1&last_event_id=51&limit=50"
                )
                self.assertEqual(200, second_page.status_code)
                self.assertEqual(
                    [{"id": 52, "event": "queued", "summary": "Job queued"}],
                    second_page.get_json()["events"],
                )
                self.assertEqual(52, second_page.get_json()["next_cursor"])
                self.assertFalse(second_page.get_json()["has_more"])
                self.assertNotIn("private-", first_page.get_data(as_text=True))
                self.assertNotIn("private-", second_page.get_data(as_text=True))
            finally:
                app.extensions["showcase_workspace_service"].close()
                app.extensions["showcase_run_service"].close()
                app.extensions["loopback_store"].close()
