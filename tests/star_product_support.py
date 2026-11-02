"""Public STAR Job fixture with finite, independently counted HTTP replies."""

import json
import os
import tempfile
import time
import uuid
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.flask_app import create_app

SOLVED = {"assessment": "SOLVED", "worked": [], "failed": [], "candidates": [],
          "solution_candidate": "2"}
POLISH = {"solution_candidate": "1+1=2"}
ACCEPT = {"verdict": "ACCEPT", "reason": "Addition"}


class RawProviderContent:
    """Script provider text without JSON-encoding it in the HTTP fixture."""

    def __init__(self, content):
        self.content = content


class StarJobFixture:
    def open_star(self, replies, *, retry=1, **config):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.data_dir = folder.name
        self.enterContext(patch.dict(os.environ, {"INTERN_API_KEY": "scripted-only"}))
        self.outbound = []
        self.outbound_messages = []
        self.replies = list(replies)

        def respond(*args, **kwargs):
            request = json.loads(kwargs["data"])
            context = json.loads(request["messages"][-1]["content"])
            self.outbound.append(context)
            self.outbound_messages.append(request["messages"])
            value = self.replies.pop(0)
            if isinstance(value, BaseException):
                raise value
            if callable(value):
                value = value(context)

            class Reply:
                status_code = 200

                def raise_for_status(self):
                    pass

                def json(self):
                    content = value.content if isinstance(value, RawProviderContent) else json.dumps(value)
                    return {"choices": [{"finish_reason": "stop", "message": {
                        "content": content}}], "model": "intern-s2",
                        "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}

            return Reply()

        self.post = self.enterContext(patch("llm_client.requests.post", side_effect=respond))
        self.app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": folder.name,
            "SHOWCASE_JOB_DELAY_SECONDS": 0, "SHOWCASE_STAR_ENABLED": True,
            "SHOWCASE_STAR_ADAPTER": InternModelAdapter(InternChatClient(retry=retry), max_tokens=256),
            "SHOWCASE_STAR_EVIDENCE_KIND": "fault_injection", **config})
        for name in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            self.addCleanup(self.app.extensions[name].close)
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
        self.session = self.client.post("/api/new_chat", headers=self.headers()).get_json()["new_session_id"]

    def headers(self):
        return {"X-CSRF-Token": self.csrf, "Idempotency-Key": str(uuid.uuid4())}

    def create_job(self):
        response = self.client.post("/api/agent/jobs", json={"message": "1+1",
            "session_id": self.session, "solver_mode": "star_limited"}, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        return response.get_json()["job_id"]

    def wait_for(self, predicate):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(.01)
        self.fail("public STAR observation timed out")

    def job(self, job_id):
        return self.client.get(f"/api/agent/jobs/{job_id}").get_json()

    def terminal(self, job_id):
        return self.wait_for(lambda: (job if (job := self.job(job_id))["status"] in {
            "succeeded", "failed", "canceled"} else None))

    def report(self, job_id):
        return self.client.get(f"/api/agent/jobs/{job_id}/report").get_json()["report"]

    def cancel(self, job_id):
        result = self.client.post(f"/api/agent/jobs/{job_id}/cancel", json={}, headers=self.headers())
        self.assertEqual(200, result.status_code, result.get_json())
        return result.get_json()
