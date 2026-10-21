from __future__ import annotations

import os
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.flask_app import create_app
from showcase.live_pipeline import LiveAgentPipeline, PipelineBudget
from showcase.tools import ToolRegistry


class Response:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {
            "choices": [{"finish_reason": "stop", "message": {"content": "2"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        }


class RunBudgetContractTest(unittest.TestCase):
    def run_job(self, *, budget=None, responses=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.enterContext(patch.dict(os.environ, {"INTERN_API_KEY": "fake-key"}))
        post = self.enterContext(patch("llm_client.requests.post", side_effect=responses, return_value=Response()))
        self.enterContext(patch("llm_client.time.sleep"))
        pipeline = LiveAgentPipeline(
            InternModelAdapter(InternChatClient(retry=2), max_tokens=256),
            ToolRegistry(), budget=budget,
        )
        app = create_app({"TESTING": True, "SHOWCASE_MODE": "live",
                          "SHOWCASE_DATA_DIR": directory.name, "SHOWCASE_LIVE_PIPELINE": pipeline})
        for key in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            self.addCleanup(app.extensions[key].close)
        client = app.test_client()
        csrf = client.get("/api/check_auth").get_json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}
        session = client.post("/api/new_chat", headers=headers).get_json()["new_session_id"]
        job_id = client.post("/api/agent/jobs", json={"message": "1+1", "session_id": session},
                             headers=headers).get_json()["job_id"]
        for _ in range(300):
            job = client.get(f"/api/agent/jobs/{job_id}").get_json()
            if job["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.01)
        report = client.get(f"/api/agent/jobs/{job_id}/report").get_json()["report"]
        evidence = client.get(f"/api/runs/{job_id}/evidence").get_json()
        return job, report, evidence, post

    def test_provider_usage_settles_reservations_in_persisted_report(self):
        job, report, evidence, post = self.run_job()
        self.assertEqual("succeeded", job["status"])
        ledger = report["budget"]
        self.assertEqual(3, ledger["logical_calls"])
        self.assertEqual(3, ledger["http_attempts"])
        self.assertEqual({"prompt_tokens": 21, "completion_tokens": 9, "total_tokens": 30}, ledger["provider_known"])
        self.assertEqual(0, ledger["reserved_tokens"])
        self.assertEqual(0, ledger["unknown_attempts"])
        self.assertIsNone(ledger["cost"])
        self.assertEqual(ledger, evidence["budget"])
        self.assertEqual(3, post.call_count)

    def test_retry_timeout_keeps_unknown_reservation_and_consumes_attempt_budget(self):
        from requests import Timeout

        job, report, _evidence, post = self.run_job(
            budget=PipelineBudget(max_http_attempts=1), responses=[Timeout("private"), Response()],
        )
        self.assertEqual("failed", job["status"])
        self.assertEqual(1, post.call_count)
        ledger = report["budget"]
        self.assertEqual(1, ledger["logical_calls"])
        self.assertEqual(1, ledger["http_attempts"])
        self.assertEqual(1, ledger["unknown_attempts"])
        self.assertEqual(1, ledger["unresolved_attempts"])
        self.assertGreaterEqual(ledger["reserved_tokens"], 256)
        self.assertIsNone(ledger["provider_known"]["total_tokens"])

    def test_input_plus_output_reservation_blocks_dispatch_before_http(self):
        job, report, _evidence, post = self.run_job(budget=PipelineBudget(max_tokens=256))
        self.assertEqual("failed", job["status"])
        self.assertEqual(0, post.call_count)
        self.assertEqual(0, report["budget"]["http_attempts"])

    def test_missing_usage_is_not_free_and_exhausts_next_reservation(self):
        class MissingUsage(Response):
            def json(self):
                result = super().json()
                del result["usage"]
                return result

        job, report, _evidence, post = self.run_job(
            budget=PipelineBudget(max_tokens=850), responses=[MissingUsage(), Response(), Response()],
        )
        self.assertEqual("failed", job["status"])
        self.assertEqual(1, post.call_count)
        self.assertEqual(1, report["budget"]["unknown_attempts"])
        self.assertGreater(report["budget"]["reserved_tokens"], 256)
        self.assertIsNone(report["budget"]["provider_known"]["prompt_tokens"])
