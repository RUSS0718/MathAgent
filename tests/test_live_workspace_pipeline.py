from __future__ import annotations

import tempfile
import time
import unittest
import uuid
from pathlib import Path

from showcase.flask_app import create_app


class StubLivePipeline:
    def run(self, run_id, problem, *, verification_mode, emit):
        del problem, verification_mode
        emit({
            "type": "node_start",
            "job_id": run_id,
            "step_id": "planner",
            "node_name": "planner",
            "title": "规划器",
            "summary": "已调用真实 pipeline seam",
        })
        emit({
            "type": "final_result",
            "job_id": run_id,
            "node_name": "terminal",
            "step_id": "terminal",
            "title": "任务完成",
            "data": {"type": "text", "summary": "答案"},
        })
        return {
            "status": "COMPLETED",
            "stage": "completed",
            "final_response": "答案",
            "summary": "stub live pipeline",
            "tool_results": [],
            "verification": {"status": "unknown", "findings": ["no_tool_evidence"]},
        }


class LiveWorkspacePipelineTest(unittest.TestCase):
    def test_live_job_uses_pipeline_and_persists_node_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = create_app({
                "TESTING": True,
                "SHOWCASE_MODE": "live",
                "SHOWCASE_DATA_DIR": str(Path(directory) / "showcase"),
                "SHOWCASE_LIVE_PIPELINE": StubLivePipeline(),
            })
            client = app.test_client()
            csrf = client.get("/api/check_auth").get_json()["csrf_token"]
            session_id = client.post("/api/new_chat", headers={"X-CSRF-Token": csrf}).get_json()["new_session_id"]
            response = client.post(
                "/api/agent/jobs",
                json={"message": "求解 x+1=2", "session_id": session_id},
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())},
            )
            job_id = response.get_json()["job_id"]
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                job = client.get(f"/api/agent/jobs/{job_id}").get_json()
                if job["status"] in {"succeeded", "failed", "canceled"}:
                    break
                time.sleep(0.01)
            self.assertEqual("succeeded", job["status"])
            check = job["result"]["verification"]
            self.assertTrue(check["artifact"]["sha256"])
            self.assertEqual(check, client.get(f"/api/runs/{job_id}").get_json()["result"]["verification"])
            self.assertEqual(check, client.get(f"/api/runs/{job_id}/evidence").get_json()["verification"])
            stream = client.get(f"/api/agent/jobs/{job_id}/events?last_event_id=0").data.decode()
            self.assertIn("event: node_start", stream)
            self.assertIn("event: final_result", stream)
            self.assertEqual("答案", client.get(f"/api/agent/jobs/{job_id}/report").get_json()["report"]["answer"])
            app.extensions["showcase_workspace_service"].close()
            app.extensions["showcase_run_service"].close()
            app.extensions["loopback_store"].close()


if __name__ == "__main__":
    unittest.main()
