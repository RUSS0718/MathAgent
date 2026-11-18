"""Public Job acceptance for frozen streaming recovery and terminal races."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import requests

from llm_client import InternChatClient
from showcase.adapters import InternStreamAdapter
from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture

POLICY_VERSION = "faithful-stream-v1"
POLICY = {
    "policy_version": POLICY_VERSION,
    "soft_prompt_seconds": 1200,
    "effective_idle_seconds": 30,
}


class FaithfulS01RecoveryAcceptance(StarJobFixture, unittest.TestCase):
    """Exercise the enabled policy only through public Jobs and real restarts."""

    def open_frozen_stream(self, replies, **config):
        """Create a controlled stream Job with the S01 policy enabled."""
        adapter = config.pop(
            "SHOWCASE_STAR_ADAPTER",
            InternStreamAdapter(InternChatClient(retry=1), max_tokens=256),
        )
        features = {"stream_activity": True, "strict_completion": True}
        features.update(config.pop("SHOWCASE_STAR_FEATURES", {}))
        self.open_star(
            replies,
            SHOWCASE_STAR_ADAPTER=adapter,
            SHOWCASE_STREAM_TIMEOUT_POLICY_VERSION=POLICY_VERSION,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_runtime_seconds=120),
            SHOWCASE_STAR_FEATURES=features,
            **config,
        )

    def assert_frozen_attempts(self, job):
        """Require evidence from calls that actually traversed the new adapter policy."""
        attempts = job["result"]["request_attempts"]
        self.assertTrue(attempts)
        for attempt in attempts:
            self.assertEqual(POLICY_VERSION,
                             attempt["call_policy_evidence"]["policy_version"], attempt)

    def reopened_stream_app(self, folder, cleanup):
        """Open the same persisted Job with the server-side policy now disabled."""
        from contextlib import ExitStack

        from showcase.flask_app import create_app
        from tests.faithful_s01_recovery_worker import app_config
        from tests.star_recovery_worker import stream_transport

        transport = stream_transport(folder, "after")
        self.enterContext(patch.dict(os.environ, {"INTERN_API_KEY": "scripted-only"}))
        stack = self.enterContext(ExitStack())
        stack.enter_context(patch("showcase.adapters.requests.post", side_effect=transport))
        stack.enter_context(patch(
            "showcase.request_transport.strict_loopback_post", side_effect=transport
        ))
        app = create_app(app_config(folder, freeze_policy=False))
        cleanup.callback(self.close_app, app)
        self.app = app
        self.client = app.test_client()
        self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
        return app

    @staticmethod
    def close_app(app):
        """Close reopened services before their temporary SQLite directory is removed."""
        for name in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
            app.extensions[name].close()

    def run_worker(self, folder, window):
        """Start the dedicated crash worker and require its intentional exit."""
        result = subprocess.run(
            [sys.executable, "-m", "tests.faithful_s01_recovery_worker", str(folder), window],
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(71, result.returncode, result.stderr.decode(errors="replace"))

    def test_same_key_create_replay_returns_original_job_and_frozen_policy(self):
        self.open_frozen_stream([SOLVED, POLISH, ACCEPT])
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original_post = self.post.side_effect

        def delayed_post(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise AssertionError("scripted response was not released")
            return original_post(*args, **kwargs)

        self.post.side_effect = delayed_post
        key = str(uuid.uuid4())
        headers = {"X-CSRF-Token": self.csrf, "Idempotency-Key": key}
        payload = {"message": "1+1", "session_id": self.session, "solver_mode": "star_limited"}
        first = self.client.post("/api/agent/jobs", json=payload, headers=headers)
        self.assertEqual(202, first.status_code, first.get_json())
        job_id = first.get_json()["job_id"]
        self.assertTrue(entered.wait(5))
        budget_before_replay = self.job(job_id)["result"]["budget"]
        replay = self.client.post("/api/agent/jobs", json=payload, headers=headers)
        self.assertEqual(200, replay.status_code, replay.get_json())
        self.assertTrue(replay.get_json()["existing"])
        self.assertEqual(job_id, replay.get_json()["job_id"])
        self.assertEqual(0, len(self.outbound))
        budget_after_replay = self.job(job_id)["result"]["budget"]
        for key in ("deadline_at", "reserved_tokens", "unknown_attempts"):
            self.assertEqual(budget_before_replay[key], budget_after_replay[key])
        release.set()

        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual(POLICY, final["result"]["budget"]["stream_timeout_policy"])
        self.assert_frozen_attempts(final)
        self.assertEqual(3, len(self.outbound))
        self.assertEqual("same_artifact", self.report(job_id)["checks"]["binding"])

    def test_process_exit_mid_stream_keeps_unknown_and_explicit_retry_identity(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as cleanup:
            folder = Path(directory)
            self.run_worker(folder, "stream_exit")
            job_id = (folder / "job_id").read_text(encoding="utf-8")
            before = [json.loads(line) for line in
                      (folder / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(1, len(before))

            self.reopened_stream_app(folder, cleanup)
            failed = self.terminal(job_id)
            self.assertEqual("failed", failed["status"])
            self.assertEqual(POLICY, failed["result"]["budget"]["stream_timeout_policy"])
            self.assert_frozen_attempts(failed)
            recovery = failed["result"]["solver"]["recovery"]
            self.assertEqual("needs_review", recovery["status"])
            self.assertEqual(1, len(recovery["unknown_calls"]))
            old_id = recovery["unknown_calls"][0]["call_id"]
            original_budget = failed["result"]["budget"]
            self.assertEqual(1, original_budget["unknown_attempts"])
            self.assertGreater(original_budget["reserved_tokens"], 0)

            ordinary = self.client.post(
                f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers()
            )
            self.assertEqual(409, ordinary.status_code)
            self.assertEqual(1, len((folder / "requests.jsonl").read_text().splitlines()))

            new_id = str(uuid.uuid4())
            retried = self.client.post(
                f"/api/agent/jobs/{job_id}/resume",
                json={"retry_call": {"call_id": old_id, "new_call_id": new_id}},
                headers=self.headers(),
            )
            self.assertEqual(202, retried.status_code, retried.get_json())
            final = self.terminal(job_id, timeout=25)
            self.assertEqual("succeeded", final["status"], final)
            self.assertEqual(POLICY, final["result"]["budget"]["stream_timeout_policy"])
            self.assert_frozen_attempts(final)
            budget = final["result"]["budget"]
            self.assertEqual(original_budget["deadline_at"], budget["deadline_at"])
            self.assertEqual(original_budget["reserved_tokens"], budget["reserved_tokens"])
            self.assertEqual(1, budget["unknown_attempts"])
            retries = final["result"]["solver"]["recovery"]["retries"]
            self.assertEqual(old_id, retries[0]["retry_of"])
            self.assertNotEqual(old_id, retries[0]["call_id"])
            requests_after = [json.loads(line) for line in
                              (folder / "requests.jsonl").read_text().splitlines()]
            self.assertEqual(2, sum(item["role"] == "explore" for item in requests_after))
            self.assertEqual(1, sum(item["role"] == "planner" for item in requests_after))
            self.assertEqual(11, len(requests_after))
            self.assertEqual("same_artifact", self.report(job_id)["checks"]["binding"])

    def test_completed_stream_receipt_is_reused_after_process_exit(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as cleanup:
            folder = Path(directory)
            self.run_worker(folder, "receipt_exit")
            job_id = (folder / "job_id").read_text(encoding="utf-8")
            before = [json.loads(line) for line in
                      (folder / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertGreaterEqual(len(before), 6)
            self.assertEqual(1, sum(item.get("role") == "explore" for item in before))

            self.reopened_stream_app(folder, cleanup)
            crashed = self.job(job_id)
            self.assertEqual(POLICY, crashed["result"]["budget"]["stream_timeout_policy"])
            self.assert_frozen_attempts(crashed)
            original_deadline = crashed["result"]["budget"]["deadline_at"]
            resumed = self.client.post(
                f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers()
            )
            self.assertEqual(202, resumed.status_code,
                             {"response": resumed.get_json(), "recovery": crashed["result"]["solver"]["recovery"]})
            final = self.terminal(job_id, timeout=25)
            self.assertEqual("succeeded", final["status"], final)
            self.assertEqual(original_deadline, final["result"]["budget"]["deadline_at"])
            requests_after = [json.loads(line) for line in
                              (folder / "requests.jsonl").read_text().splitlines()]
            self.assertEqual(1, sum(item["role"] == "explore" for item in requests_after))
            self.assertEqual(1, sum(item.get("role") == "step_verifier"
                                    and item.get("step", {}).get("step_id") == "s2"
                                    for item in requests_after))
            self.assertEqual("same_artifact", self.report(job_id)["checks"]["binding"])
            self.assert_frozen_attempts(final)

    def test_complete_invalid_stream_is_known_protocol_failure_under_policy(self):
        invalid = {**SOLVED, "confidence": 0.95}
        self.open_frozen_stream([invalid, invalid])
        job_id = self.create_job()
        failed = self.terminal(job_id)
        self.assertEqual("failed", failed["status"])
        recovery = failed["result"]["solver"]["recovery"]
        self.assertEqual([], recovery["unknown_calls"])
        self.assertEqual(2, len(recovery["protocol_failures"]))
        self.assertEqual({"invalid_role_schema"},
                         {item["error_category"] for item in recovery["protocol_failures"]})
        self.assertEqual({"protocol_failed"},
                         {item["status"] for item in recovery["protocol_failures"]})
        self.assertEqual({"stop"},
                         {item["finish_reason"] for item in recovery["protocol_failures"]})
        self.assertEqual({10},
                         {item["usage"]["total_tokens"] for item in recovery["protocol_failures"]})
        self.assert_frozen_attempts(failed)
        self.assertEqual(0, failed["result"]["budget"]["unknown_attempts"])
        self.assertEqual(2, len(self.outbound))
        rejected = self.client.post(
            f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers()
        )
        self.assertEqual(409, rejected.status_code)
        self.assertEqual(2, len(self.outbound))

    def test_cancelled_frozen_stream_only_settles_late_usage(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def delayed(_context):
            entered.set()
            if not release.wait(5):
                raise AssertionError("delayed provider response was not released")
            return SOLVED

        self.open_frozen_stream([delayed])
        job_id = self.create_job()
        self.assertTrue(entered.wait(5))
        self.cancel(job_id)
        canceled = self.job(job_id)
        solver_before = canceled["result"]["solver"]
        math_before = {key: solver_before.get(key) for key in (
            "phase", "plan", "proofs", "candidate_history", "whole_solution_reviews"
        )}
        answer_before = canceled["result"].get("final_response")
        release.set()
        settled = self.wait_for(
            lambda: self.job(job_id)
            if self.job(job_id)["result"]["budget"]["provider_known"]["total_tokens"] == 10
            else None
        )
        self.assertEqual("canceled", settled["status"])
        math_after = {key: settled["result"]["solver"].get(key) for key in math_before}
        self.assertEqual(math_before, math_after)
        self.assertEqual(answer_before, settled["result"].get("final_response"))
        self.assert_frozen_attempts(settled)
        self.assertEqual(1, len(self.outbound))
        self.assertEqual(0, settled["result"]["budget"]["reserved_tokens"])

    def test_late_complete_receipt_after_recovery_cannot_reopen_successful_job(self):
        from showcase.request_transport import response_events as real_response_events

        callbacks = []
        calls = 0

        def timeout_first_call(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                callbacks.append(kwargs["on_late_response"])
                raise requests.ReadTimeout("scripted stream disconnect")
                yield
            yield from real_response_events(*args, **kwargs)

        self.open_frozen_stream([SOLVED, POLISH, ACCEPT])
        with patch("showcase.request_transport.response_events", side_effect=timeout_first_call):
            job_id = self.create_job()
            failed = self.terminal(job_id)
            self.assertEqual("needs_review", failed["result"]["solver"]["recovery"]["status"])
            old_id = failed["result"]["solver"]["recovery"]["unknown_calls"][0]["call_id"]
            retried = self.client.post(
                f"/api/agent/jobs/{job_id}/resume",
                json={"retry_call": {"call_id": old_id, "new_call_id": str(uuid.uuid4())}},
                headers=self.headers(),
            )
            self.assertEqual(202, retried.status_code, retried.get_json())
            completed = self.terminal(job_id)
            self.assertEqual("succeeded", completed["status"], completed)
            frozen_solver = completed["result"]["solver"]
            answer = completed["result"]["final_response"]
            attempts_before = completed["result"]["request_attempts"]

            class LateReply:
                status_code = 200

            packet = {"choices": [{"delta": {"content": json.dumps(SOLVED)},
                                  "finish_reason": "stop"}],
                      "usage": {"prompt_tokens": 7, "completion_tokens": 3,
                                "total_tokens": 10}}
            late_body = ("data: " + json.dumps(packet) + "\n\ndata: [DONE]\n\n").encode()
            callbacks[0](LateReply(), late_body, .01, .2, True)
            settled = self.job(job_id)

        self.assertEqual("succeeded", settled["status"])
        self.assertEqual(frozen_solver, settled["result"]["solver"])
        self.assertEqual(answer, settled["result"]["final_response"])
        self.assertEqual(3, len(self.outbound))
        self.assertEqual("success", settled["result"]["request_attempts"][0]["status"])
        self.assertEqual("same_artifact", self.report(job_id)["checks"]["binding"])
        self.assertEqual(POLICY_VERSION,
                         attempts_before[0]["call_policy_evidence"]["policy_version"])

if __name__ == "__main__":
    unittest.main()
