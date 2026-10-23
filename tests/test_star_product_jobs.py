"""STAR integration at authenticated Job/Run HTTP and actual Adapter transport."""

import json
import os
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.flask_app import create_app


class StarProductJobsTest(unittest.TestCase):
    def open_app(self, directory, **config):
        app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": directory,
                          "SHOWCASE_JOB_DELAY_SECONDS": 0, **config})
        for name in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            self.addCleanup(app.extensions[name].close)
        client = app.test_client()
        csrf = client.get("/api/check_auth").get_json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}
        session = client.post("/api/new_chat", headers=headers).get_json()["new_session_id"]
        return app, client, headers, session

    def test_limited_job_crosses_adapter_and_fresh_review_with_one_identity(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.enterContext(patch.dict(os.environ, {"INTERN_API_KEY": "test-key"}))
        replies = [
            {"assessment": "SOLVED", "worked": ["addition"], "failed": [],
             "candidates": [], "solution_candidate": "draft: 2"},
            {"solution_candidate": "1 + 1 = 2."},
            {"verdict": "ACCEPT", "reason": "Direct addition."},
        ]

        class Response:
            status_code = 200
            def raise_for_status(self):
                pass
            def json(self):
                return {"choices": [{"finish_reason": "stop", "message": {
                    "content": json.dumps(replies.pop(0))}}], "model": "intern-s2",
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}

        post = self.enterContext(patch("llm_client.requests.post", side_effect=lambda *a, **kw: Response()))
        app, client, headers, session = self.open_app(directory.name,
            SHOWCASE_STAR_ENABLED=True,
            SHOWCASE_STAR_ADAPTER=InternModelAdapter(InternChatClient(retry=1), max_tokens=256),
            SHOWCASE_STAR_EVIDENCE_KIND="scripted")
        response = client.post("/api/agent/jobs", json={"message": "1+1",
            "session_id": session, "solver_mode": "star_limited"}, headers=headers)
        self.assertEqual(202, response.status_code, response.get_json())
        run_id = response.get_json()["job_id"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = client.get(f"/api/agent/jobs/{run_id}").get_json()
            if job["status"] in {"succeeded", "failed", "canceled"}:
                break
            time.sleep(.01)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(3, post.call_count)
        requests = [json.loads(json.loads(call.kwargs["data"])["messages"][-1]["content"]) for call in post.call_args_list]
        self.assertEqual(["explore", "explore_polish", "whole_solution_verifier"], [r["role"] for r in requests])
        self.assertTrue(all(r["run_id"] == run_id and r["original_problem"] == "1+1" for r in requests))
        self.assertEqual(requests[0]["session_key"], requests[1]["session_key"])
        self.assertNotEqual(requests[1]["session_key"], requests[2]["session_key"])
        self.assertEqual("1 + 1 = 2.", requests[2]["solution_candidate"])
        result = job["result"]
        self.assertEqual("star_limited", result["solver_mode"])
        self.assertEqual("scripted", result["evidence_kind"])
        self.assertIn("isolated_python_output_guard", result["missing_capabilities"])
        self.assertEqual(3, result["budget"]["logical_calls"])
        self.assertEqual(3, result["budget"]["http_attempts"])
        self.assertEqual(run_id, result["solver"]["run_id"])
        self.assertEqual(run_id, result["solver"]["checkpoint_thread_id"])
        run = client.get(f"/api/runs/{run_id}").get_json()
        self.assertEqual(result["solver"], run["result"]["solver"])
        self.assertEqual("1 + 1 = 2.", client.get(f"/api/agent/jobs/{run_id}/report").get_json()["report"]["answer"])
        stream = client.get(f"/api/agent/jobs/{run_id}/events").data.decode()
        self.assertIn("solution_review_assessed", stream)
        self.assertIn("solver_revision", stream)
        self.assertNotIn("original_problem", stream)
        event_ids = [json.loads(line[6:])["solver_event_id"] for line in stream.splitlines()
                     if line.startswith("data: ") and '"solver_event_id"' in line]
        self.assertEqual(len(event_ids), len(set(event_ids)))
        # Read-only public replay/export must never re-enter the solver.
        evidence = client.get(f"/api/runs/{run_id}/evidence").get_json()
        self.assertEqual("1 + 1 = 2.", evidence["run"]["final_response"])
        self.assertEqual("star_limited", evidence["mode"])
        self.assertEqual(result["solver"], evidence["solver"]["solver"])
        reopened = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": directory.name})
        try:
            other = reopened.test_client()
            other.get("/api/check_auth")
            persisted = other.get(f"/api/agent/jobs/{run_id}").get_json()
            self.assertEqual(result["solver"], persisted["result"]["solver"])
            self.assertEqual(result["budget"], persisted["result"]["budget"])
        finally:
            for name in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
                reopened.extensions[name].close()
        self.assertEqual(3, post.call_count)

    def test_rejected_review_cannot_deliver_draft_as_success(self):
        self.assert_rejected_review({"verdict": "REJECT", "reason": "Wrong addition."})

    def test_malformed_review_cannot_deliver_draft_as_success(self):
        self.assert_rejected_review({"verdict": "INVALID"})

    def assert_rejected_review(self, review_reply):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.enterContext(patch.dict(os.environ, {"INTERN_API_KEY": "test-key"}))
        replies = [
            {"assessment": "SOLVED", "worked": [], "failed": [], "candidates": [],
             "solution_candidate": "wrong draft"},
            {"solution_candidate": "wrong polished answer"},
            review_reply,
        ]
        class Response:
            status_code = 200
            def raise_for_status(self):
                pass
            def json(self):
                return {"choices": [{"finish_reason": "stop", "message": {
                    "content": json.dumps(replies.pop(0))}}]}
        post = self.enterContext(patch("llm_client.requests.post", side_effect=lambda *a, **kw: Response()))
        _, client, headers, session = self.open_app(directory.name,
            SHOWCASE_STAR_ENABLED=True,
            SHOWCASE_STAR_ADAPTER=InternModelAdapter(InternChatClient(retry=1), max_tokens=256),
            SHOWCASE_STAR_EVIDENCE_KIND="fault_injection")
        response = client.post("/api/agent/jobs", json={"message": "1+1",
            "session_id": session, "solver_mode": "star_limited"}, headers=headers)
        run_id = response.get_json()["job_id"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = client.get(f"/api/agent/jobs/{run_id}").get_json()
            if job["status"] == "failed":
                break
            time.sleep(.01)
        self.assertEqual("failed", job["status"])
        self.assertNotEqual("wrong polished answer", job["result"]["final_response"])
        self.assertEqual("unknown", job["result"]["verification"]["status"])
        self.assertEqual(3, post.call_count)
        self.assertEqual(3, job["result"]["budget"]["logical_calls"])
        self.assertEqual(3, job["result"]["budget"]["http_attempts"])
        self.assertEqual(3, job["result"]["budget"]["provider_unknown_fields"]["total_tokens"])

    def test_unsupported_and_incomplete_modes_reject_before_enqueue(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        _, client, headers, session = self.open_app(directory.name)
        for mode, code in (("typo", 400), ("star_ablation", 400),
                           ("star_reference", 503), ("star_best_effort", 503)):
            with self.subTest(mode=mode):
                response = client.post("/api/agent/jobs", json={
                    "message": "1+1", "session_id": session, "solver_mode": mode,
                }, headers=headers)
                self.assertEqual(code, response.status_code, response.get_json())
        self.assertEqual([], client.get("/api/agent/jobs/active").get_json()["jobs"])
        self.assertEqual([], client.post("/api/load_chat", json={"session_id": session}, headers=headers).get_json().get("messages", []))

    def test_mode_is_part_of_idempotency_and_review_cannot_be_disabled(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        _, client, headers, session = self.open_app(directory.name,
            SHOWCASE_STAR_ENABLED=True, SHOWCASE_WORKER_ENABLED=False)
        body = {"message": "1+1", "session_id": session, "solver_mode": "star_limited"}
        for extras in ({"verification_mode": "off"}, {"solver_options": {"star_routing": False}}):
            self.assertEqual(400, client.post("/api/agent/jobs", json={**body, **extras}, headers=headers).status_code)
        accepted = client.post("/api/agent/jobs", json=body, headers=headers)
        self.assertEqual(202, accepted.status_code)
        self.assertEqual(409, client.post("/api/agent/jobs", json={**body, "solver_mode": "legacy"}, headers=headers).status_code)
        run_id = accepted.get_json()["job_id"]
        self.assertEqual("star_limited", client.get(f"/api/runs/{run_id}").get_json()["result"]["solver_mode"])



if __name__ == "__main__":
    unittest.main()

