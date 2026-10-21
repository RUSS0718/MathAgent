from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.flask_app import create_app
from showcase.live_pipeline import LiveAgentPipeline
from showcase.tools import ToolRegistry


class Reply:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"finish_reason": "stop", "message": {"content": "2"}}]}


class RunControlContractTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.enterContext(patch.dict(os.environ, {"INTERN_API_KEY": "fake-key"}))
        self.entered, self.release = threading.Event(), threading.Event()
        self.addCleanup(self.release.set)
        self.post = self.enterContext(patch("llm_client.requests.post", side_effect=self.respond))
        self.transport = InternChatClient(retry=1)
        self.pipeline = LiveAgentPipeline(
            InternModelAdapter(self.transport, max_tokens=256), ToolRegistry()
        )
        self.app = create_app(
            {
                "TESTING": True,
                "SHOWCASE_MODE": "live",
                "SHOWCASE_DATA_DIR": directory.name,
                "SHOWCASE_LIVE_PIPELINE": self.pipeline,
                "SHOWCASE_JOB_DELAY_SECONDS": 0,
            }
        )
        for key in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            self.addCleanup(self.app.extensions[key].close)
        self.addCleanup(self.release.set)
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
        self.session = self.client.post("/api/new_chat", headers=self.headers()).get_json()[
            "new_session_id"
        ]

    def headers(self):
        return {"X-CSRF-Token": self.csrf, "Idempotency-Key": str(uuid.uuid4())}

    def respond(self, *args, **kwargs):
        self.entered.set()
        if not self.release.wait(3):
            raise TimeoutError("test release missing")
        return Reply()

    def create_job(self):
        return self.client.post(
            "/api/agent/jobs",
            json={"message": "1+1", "session_id": self.session},
            headers=self.headers(),
        ).get_json()["job_id"]

    def wait_job(self, job_id, status):
        for _ in range(300):
            job = self.client.get(f"/api/agent/jobs/{job_id}").get_json()
            if job["status"] == status:
                return job
            time.sleep(0.01)
        self.fail(job)

    def wait_attempt_audit(self, job_id):
        for _ in range(300):
            report = self.client.get(f"/api/agent/jobs/{job_id}/report").get_json()["report"]
            if report["request_attempts"]:
                return report
            time.sleep(0.01)
        self.fail("request attempt audit not persisted")

    def test_cancel_inflight_stops_dispatch_and_preserves_unknown_budget(self):
        job_id = self.create_job()
        self.assertTrue(self.entered.wait(2))
        response = self.client.post(
            f"/api/agent/jobs/{job_id}/cancel", json={}, headers=self.headers()
        )
        self.assertEqual("canceled", response.get_json()["status"])
        report = self.client.get(f"/api/agent/jobs/{job_id}/report").get_json()["report"]
        self.assertEqual(1, report["budget"]["unresolved_attempts"])
        self.release.set()
        self.wait_attempt_audit(job_id)
        self.assertEqual(1, self.post.call_count)
        checkpoint = self.app.extensions["showcase_run_service"].get_checkpoint(job_id)
        self.assertEqual("CANCELED", checkpoint["status"])
        self.assertEqual(
            "canceled", self.client.get(f"/api/agent/jobs/{job_id}").get_json()["status"]
        )
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertEqual(1, evidence["budget"]["http_attempts"])

    def test_safe_checkpoint_resume_does_not_repeat_planner_or_reset_budget(self):
        self.pipeline.pause_after_planner = True
        self.release.set()
        job_id = self.create_job()
        self.wait_job(job_id, "waiting_input")
        self.assertEqual(
            "WAITING_INPUT", self.client.get(f"/api/runs/{job_id}").get_json()["status"]
        )
        before = self.client.get(f"/api/agent/jobs/{job_id}/report").get_json()["report"]["budget"]
        self.assertEqual(1, before["http_attempts"])
        response = self.client.post(
            f"/api/agent/jobs/{job_id}/resume", json={"answer": "继续"}, headers=self.headers()
        )
        self.assertEqual(202, response.status_code)
        self.wait_job(job_id, "succeeded")
        report = self.client.get(f"/api/agent/jobs/{job_id}/report").get_json()["report"]
        self.assertEqual(3, report["budget"]["http_attempts"])
        self.assertEqual(before["deadline_at"], report["budget"]["deadline_at"])
        self.assertEqual(3, self.post.call_count)
        checkpoint = self.app.extensions["showcase_run_service"].get_checkpoint(job_id)
        self.assertEqual("COMPLETED", checkpoint["status"])

    def test_deadline_rejects_late_response_and_keeps_report(self):
        from showcase.live_pipeline import PipelineBudget

        self.pipeline.budget = PipelineBudget(max_runtime_seconds=1)
        job_id = self.create_job()
        self.assertTrue(self.entered.wait(2))
        time.sleep(1.05)
        self.release.set()
        job = self.wait_job(job_id, "failed")
        self.assertEqual("run_deadline_exhausted", job["error"])
        self.assertEqual(1, self.post.call_count)
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        self.assertIn("event: timeout", stream)
        report = self.client.get(f"/api/agent/jobs/{job_id}/report").get_json()["report"]
        self.assertEqual(1, report["budget"]["http_attempts"])
        self.assertEqual("", report["answer"])

    def test_restart_unknown_remote_requires_review_and_never_replays(self):
        job_id = self.create_job()
        self.assertTrue(self.entered.wait(2))
        recovered = create_app(
            {
                "TESTING": True,
                "SHOWCASE_MODE": "live",
                "SHOWCASE_DATA_DIR": self.app.config["SHOWCASE_DATA_DIR"],
                "SHOWCASE_LIVE_PIPELINE": LiveAgentPipeline(self.pipeline.model, ToolRegistry()),
                "SHOWCASE_JOB_DELAY_SECONDS": 0,
            }
        )
        for key in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            self.addCleanup(recovered.extensions[key].close)
        self.addCleanup(self.release.set)
        client = recovered.test_client()
        csrf = client.get("/api/check_auth").get_json()["csrf_token"]
        job = client.get(f"/api/agent/jobs/{job_id}").get_json()
        self.assertEqual("needs_review", job["error"])
        response = client.post(
            f"/api/agent/jobs/{job_id}/resume",
            json={},
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())},
        )
        self.assertEqual(409, response.status_code)
        report = client.get(f"/api/agent/jobs/{job_id}/report").get_json()["report"]
        self.assertEqual(1, report["budget"]["unresolved_attempts"])
        self.release.set()
        self.wait_attempt_audit(job_id)
        self.assertEqual(1, self.post.call_count)
        self.assertEqual(
            "needs_review", client.get(f"/api/agent/jobs/{job_id}").get_json()["error"]
        )

    def test_safe_checkpoint_survives_restart_and_resume(self):
        self.pipeline.pause_after_planner = True
        self.release.set()
        job_id = self.create_job()
        self.wait_job(job_id, "waiting_input")
        self.app.extensions["showcase_workspace_service"].close()
        recovered = create_app(
            {
                "TESTING": True,
                "SHOWCASE_MODE": "live",
                "SHOWCASE_DATA_DIR": self.app.config["SHOWCASE_DATA_DIR"],
                "SHOWCASE_LIVE_PIPELINE": LiveAgentPipeline(self.pipeline.model, ToolRegistry()),
            }
        )
        for key in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            self.addCleanup(recovered.extensions[key].close)
        client = recovered.test_client()
        csrf = client.get("/api/check_auth").get_json()["csrf_token"]
        response = client.post(
            f"/api/agent/jobs/{job_id}/resume",
            json={},
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())},
        )
        self.assertEqual(202, response.status_code)
        for _ in range(300):
            job = client.get(f"/api/agent/jobs/{job_id}").get_json()
            if job["status"] == "succeeded":
                break
            time.sleep(0.01)
        self.assertEqual("succeeded", job["status"])
        self.assertEqual(3, self.post.call_count)
        self.assertEqual(3, job["result"]["budget"]["logical_calls"])

    def test_cancel_prevents_http_retry_after_remote_failure(self):
        import requests

        self.transport.retry = 2

        def fail(*args, **kwargs):
            self.entered.set()
            self.release.wait(3)
            raise requests.Timeout()

        self.post.side_effect = fail
        job_id = self.create_job()
        self.assertTrue(self.entered.wait(2))
        self.client.post(f"/api/agent/jobs/{job_id}/cancel", json={}, headers=self.headers())
        self.release.set()
        report = self.wait_attempt_audit(job_id)
        self.assertEqual(1, self.post.call_count)
        self.assertEqual(1, report["budget"]["unresolved_attempts"])
        self.assertEqual(
            "canceled", self.client.get(f"/api/agent/jobs/{job_id}").get_json()["status"]
        )

    def test_cancel_inflight_tool_stops_continuation(self):
        class ToolReply(Reply):
            def json(self):
                return {
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call_math",
                                        "type": "function",
                                        "function": {"name": "math", "arguments": "{}"},
                                    }
                                ],
                            },
                        }
                    ]
                }

        self.post.side_effect = [Reply(), ToolReply()]

        def handler(arguments):
            self.entered.set()
            self.release.wait(3)
            return "2"

        self.pipeline.registry.register("math", handler)
        job_id = self.create_job()
        self.assertTrue(self.entered.wait(2))
        self.client.post(f"/api/agent/jobs/{job_id}/cancel", json={}, headers=self.headers())
        self.release.set()
        for _ in range(300):
            report = self.client.get(f"/api/agent/jobs/{job_id}/report").get_json()["report"]
            if report["budget"]["unknown_tool_calls"] == 0:
                break
            time.sleep(0.01)
        self.assertEqual(1, report["budget"]["tool_calls"])
        self.assertEqual(2, self.post.call_count)
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertEqual("math", evidence["tools"][0]["name"])
        self.assertEqual(
            "canceled", self.client.get(f"/api/agent/jobs/{job_id}").get_json()["status"]
        )

    def test_late_known_usage_settles_without_reopening_canceled_run(self):
        class MeteredReply(Reply):
            def json(self):
                return {
                    **super().json(),
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
                }

        def respond(*args, **kwargs):
            self.entered.set()
            self.release.wait(3)
            return MeteredReply()

        self.post.side_effect = respond
        job_id = self.create_job()
        self.assertTrue(self.entered.wait(2))
        self.client.post(f"/api/agent/jobs/{job_id}/cancel", json={}, headers=self.headers())
        self.release.set()
        report = self.wait_attempt_audit(job_id)
        self.assertEqual(10, report["budget"]["provider_known"]["total_tokens"])
        self.assertEqual(0, report["budget"]["reserved_tokens"])
        self.assertEqual(1, self.post.call_count)
        self.assertEqual(
            "canceled", self.client.get(f"/api/agent/jobs/{job_id}").get_json()["status"]
        )

    def test_concurrent_resume_sse_disconnect_cancel_preserves_audit(self):
        from concurrent.futures import ThreadPoolExecutor

        self.pipeline.pause_after_planner = True
        self.release.set()
        job_id = self.create_job()
        self.wait_job(job_id, "waiting_input")
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events", buffered=False)
        next(iter(stream.response))
        stream.close()
        before = self.client.get(f"/api/agent/jobs/{job_id}/report").get_json()["report"]["budget"]
        self.entered.clear()
        self.release.clear()
        barrier = threading.Barrier(2)

        def resume():
            client = self.app.test_client()
            csrf = client.get("/api/check_auth").get_json()["csrf_token"]
            barrier.wait(2)
            return client.post(
                f"/api/agent/jobs/{job_id}/resume",
                json={},
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())},
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: resume(), range(2)))
        self.assertEqual([202, 409], sorted(responses))
        self.assertTrue(self.entered.wait(2))
        self.client.post(f"/api/agent/jobs/{job_id}/cancel", json={}, headers=self.headers())
        self.release.set()
        for _ in range(300):
            report = self.client.get(f"/api/agent/jobs/{job_id}/report").get_json()["report"]
            if len(report["request_attempts"]) == 2:
                break
            time.sleep(0.01)
        self.assertEqual(2, len(report["request_attempts"]))
        self.assertEqual(2, self.post.call_count)
        self.assertEqual(before["deadline_at"], report["budget"]["deadline_at"])
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        self.assertEqual(1, stream.count("event: resumed"))
        self.assertIn("event: canceled", stream)
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertEqual(2, evidence["budget"]["http_attempts"])
        self.assertEqual("CANCELED", evidence["run"]["status"])
