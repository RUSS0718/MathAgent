"""Concurrent late metering must survive terminal audit publication."""

import os
import tempfile
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.flask_app import create_app
from showcase.live_pipeline import PipelineBudget
from showcase.request_attempts import capture_pipeline_attempts


class Response:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {
            "choices": [{"finish_reason": "stop", "message": {"content": "2"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        }


class LateMeteringContractTest(unittest.TestCase):
    def test_terminal_audit_cannot_overwrite_concurrent_provider_settlement(self):
        entered = [threading.Event(), threading.Event()]
        released = [threading.Event(), threading.Event()]
        audit_blocked, audit_continue, second_settled = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )
        clock_now = time.time()

        def index():
            return 0 if threading.current_thread().name.endswith("_0") else 1

        def post(*args, **kwargs):
            i = index()
            entered[i].set()
            released[i].wait(4)
            return Response()

        def clock():
            if (
                threading.current_thread().name == "meter-race_0"
                and released[0].is_set()
                and not audit_blocked.is_set()
            ):
                audit_blocked.set()
                audit_continue.wait(4)
            return clock_now

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"INTERN_API_KEY": "fake-key"}),
            patch("llm_client.requests.post", side_effect=post),
        ):
            model = InternModelAdapter(InternChatClient(retry=1), max_tokens=256)

            class Worker:
                @capture_pipeline_attempts
                def run(self, run_id, problem, *, emit):
                    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="meter-race") as pool:
                        futures = [
                            pool.submit(
                                copy_context().run,
                                model.complete,
                                [{"role": "user", "content": problem}],
                            )
                            for _ in range(2)
                        ]
                        for future in futures:
                            try:
                                future.result()
                            except RuntimeError:
                                pass
                    return {"status": "NEEDS_REVIEW", "error": {"category": "canceled"}}

            class Pipeline:
                budget = PipelineBudget()

                def run(self, run_id, problem, *, emit, **kwargs):
                    def audit(event):
                        if threading.current_thread().name == "meter-race_1":
                            second_settled.set()
                        emit(event)

                    return Worker().run(run_id, problem, emit=audit)

            app = create_app(
                {
                    "TESTING": True,
                    "SHOWCASE_MODE": "live",
                    "SHOWCASE_DATA_DIR": directory,
                    "SHOWCASE_LIVE_PIPELINE": Pipeline(),
                    "SHOWCASE_JOB_DELAY_SECONDS": 0,
                }
            )
            try:
                client = app.test_client()
                csrf = client.get("/api/check_auth").get_json()["csrf_token"]

                def headers():
                    return {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}

                session = client.post("/api/new_chat", headers=headers()).get_json()[
                    "new_session_id"
                ]
                job_id = client.post(
                    "/api/agent/jobs",
                    json={"message": "1+1", "session_id": session},
                    headers=headers(),
                ).get_json()["job_id"]
                self.assertTrue(all(event.wait(2) for event in entered))
                client.post(f"/api/agent/jobs/{job_id}/cancel", json={}, headers=headers())
                with patch("showcase.run_budget.time.time", side_effect=clock):
                    released[0].set()
                    self.assertTrue(audit_blocked.wait(2))
                    released[1].set()
                    self.assertTrue(second_settled.wait(2))
                    audit_continue.set()
                    for _ in range(300):
                        report = client.get(f"/api/agent/jobs/{job_id}/report").get_json()["report"]
                        if len(report["request_attempts"]) == 2:
                            break
                        time.sleep(0.01)
                self.assertEqual(20, report["budget"]["provider_known"]["total_tokens"])
                self.assertEqual(0, report["budget"]["reserved_tokens"])
                self.assertEqual(2, report["budget"]["http_attempts"])
            finally:
                for event in released + [audit_continue]:
                    event.set()
                for key in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
                    app.extensions[key].close()
