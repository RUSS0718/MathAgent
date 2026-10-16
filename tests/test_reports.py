"""Public contracts for report DTOs and evidence-only replay."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from showcase.evidence import replay_evidence
from showcase.flask_app import create_app


class ReportContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": str(Path(self.temp_dir.name) / "data")})
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.app.extensions["showcase_workspace_service"].close()
        self.app.extensions["showcase_run_service"].close()
        self.app.extensions["loopback_store"].close()
        self.temp_dir.cleanup()

    def _csrf(self) -> str:
        return self.client.get("/api/check_auth").get_json()["csrf_token"]

    def test_run_evidence_has_stable_public_report_fields_and_legacy_shape(self) -> None:
        csrf = self._csrf()
        created = self.client.post("/api/runs", json={"problem": "计算 1+1"}, headers={"X-CSRF-Token": csrf})
        run_id = created.get_json()["run_id"]

        first = self.client.get(f"/api/runs/{run_id}/evidence")
        second = self.client.get(f"/api/runs/{run_id}/evidence")
        self.assertEqual(200, first.status_code)
        body = first.get_json()
        self.assertEqual(body, second.get_json())
        self.assertEqual("evidence-v0.1", body["version"])
        self.assertEqual(run_id, body["evidence_id"])
        self.assertEqual("fake", body["mode"])
        self.assertIn("answer", body["report"])
        self.assertIn("limitations", body["report"])
        self.assertIn("timeline", body)

    def test_replay_reads_saved_pack_without_provider_or_tool_calls(self) -> None:
        pack = {"version": "evidence-v0.2", "evidence_id": "ev_saved", "mode": "fake", "report": {"answer": "2"}}
        result = replay_evidence(pack)
        self.assertEqual("replay", result["mode"])
        self.assertEqual("ev_saved", result["evidence_id"])
        self.assertEqual("2", result["report"]["answer"])

        response = self.client.post("/api/evidence/replay", json=pack, headers={"X-CSRF-Token": self._csrf()})
        self.assertEqual(200, response.status_code)
        self.assertEqual("replay", response.get_json()["mode"])

    def test_job_report_is_available_from_same_event_source(self) -> None:
        csrf = self._csrf()
        session_id = self.client.post("/api/new_chat", headers={"X-CSRF-Token": csrf}).get_json()["new_session_id"]
        created = self.client.post(
            "/api/agent/jobs",
            json={"message": "计算 2+2", "session_id": session_id},
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": "1f8f2e35-7c43-4b23-a0ef-03f4bf8d05d5"},
        )
        job_id = created.get_json()["job_id"]
        for _ in range(50):
            report = self.client.get(f"/api/agent/jobs/{job_id}/report")
            if report.get_json().get("status") == "succeeded":
                break
            time.sleep(0.01)
        self.assertEqual(200, report.status_code)
        body = report.get_json()
        self.assertEqual(job_id, body["evidence_id"])
        self.assertIn(body["mode"], {"fake", "live", "replay", "experimental", "unavailable", "planned"})
        self.assertEqual("succeeded", body["status"])
        self.assertIn("tool_summaries", body["report"])


if __name__ == "__main__":
    unittest.main()
