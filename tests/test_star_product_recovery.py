"""Public STAR recovery and explicit unknown decisions."""

import unittest
import uuid

import requests

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture


class StarRecoveryTest(StarJobFixture, unittest.TestCase):
    def test_unknown_requires_explicit_new_identity_and_keeps_original_budget(self):
        self.open_star([requests.Timeout("outcome unknown"), SOLVED, POLISH, ACCEPT],
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=6, max_http_attempts=6))
        job_id = self.create_job()
        first = self.terminal(job_id)
        self.assertEqual("failed", first["status"])
        old_budget = first["result"]["budget"]
        decisions = first["result"]["solver"]["recovery"]
        self.assertEqual("needs_review", decisions["status"])
        old_id = decisions["unknown_calls"][0]["call_id"]
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers())
        self.assertEqual(409, response.status_code)
        bypass = self.client.post(f"/api/runs/{job_id}/resume", json={}, headers=self.headers())
        self.assertEqual(409, bypass.status_code)
        self.assertEqual(1, len(self.outbound))
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={
            "retry_call": {"call_id": old_id, "new_call_id": str(uuid.uuid4())}}, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual(4, len(self.outbound))
        budget = final["result"]["budget"]
        self.assertEqual(old_budget["deadline_at"], budget["deadline_at"])
        self.assertEqual(4, budget["http_attempts"])
        self.assertEqual(1, budget["unknown_attempts"])
        self.assertEqual(old_budget["reserved_tokens"], budget["reserved_tokens"])
        self.assertEqual(old_id, final["result"]["solver"]["recovery"]["retries"][0]["retry_of"])
        self.client.get(f"/api/agent/jobs/{job_id}/events", headers={"Last-Event-ID": "1"})
        self.client.get(f"/api/runs/{job_id}/evidence")
        self.assertEqual(4, len(self.outbound))

    def test_process_exit_after_second_acceptance_resumes_third_step(self):
        self.assert_process_window("accepted")

    def test_process_exit_after_recorded_verifier_response_reuses_it(self):
        self.assert_process_window("response")

    def test_process_exit_after_session_exchange_does_not_repeat_acceptance(self):
        self.assert_process_window("exchange")

    def test_process_exit_inflight_requires_explicit_new_identity(self):
        self.assert_process_window("unknown")

    def test_process_exit_after_tool_receipt_does_not_repeat_tool(self):
        self.assert_process_window("tool")

    def test_process_exit_inside_tool_refuses_unsafe_replay(self):
        self.assert_process_window("tool_unknown")

    def assert_process_window(self, window):
        import json
        import os
        from pathlib import Path
        import subprocess
        import sys
        import tempfile
        from unittest.mock import patch
        from showcase.flask_app import create_app
        from tests.star_recovery_worker import config, provider

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            process = subprocess.run([sys.executable, "-m", "tests.star_recovery_worker", directory, window],
                                     capture_output=True, timeout=30)
            self.assertEqual(71, process.returncode, process.stderr.decode(errors="replace"))
            job_id = (folder / "job_id").read_text()
            before = [json.loads(line) for line in (folder / "requests.jsonl").read_text().splitlines()]
            self.assertEqual(5 if window in {"tool", "tool_unknown"} else 6, len(before))
            with patch.dict(os.environ, {"INTERN_API_KEY": "scripted-only"}), patch(
                    "llm_client.requests.post", side_effect=lambda *a, **kw: provider(folder, kw)):
                app = create_app(config(folder))
                try:
                    self.app = app
                    self.client = app.test_client()
                    self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
                    original = self.job(job_id)["result"]["budget"]
                    if window == "tool_unknown":
                        recovery = self.job(job_id)["result"]["solver"]["recovery"]
                        self.assertEqual("needs_review", recovery["status"])
                        self.assertEqual(1, len(recovery["unknown_tools"]))
                        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers())
                        self.assertEqual(409, response.status_code)
                        self.assertEqual("star_tool_recovery_needs_review", response.get_json()["error"])
                        self.assertEqual(1, self.job(job_id)["result"]["budget"]["tool_calls"])
                        self.assertEqual(5, len((folder / "requests.jsonl").read_text().splitlines()))
                        return
                    decision = {}
                    if window == "unknown":
                        unknown = self.job(job_id)["result"]["solver"]["recovery"]["unknown_calls"]
                        rejected = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers())
                        self.assertEqual(409, rejected.status_code)
                        self.assertEqual(1, len(unknown))
                        decision = {"retry_call": {"call_id": unknown[0]["call_id"],
                                                   "new_call_id": str(uuid.uuid4())}}
                    response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json=decision, headers=self.headers())
                    self.assertEqual(202, response.status_code, response.get_json())
                    final = self.terminal(job_id)
                    self.assertEqual("succeeded", final["status"], final)
                    after = [json.loads(line) for line in (folder / "requests.jsonl").read_text().splitlines()]
                    self.assertEqual(11 if window == "unknown" else 10, len(after))
                    if window == "tool":
                        self.assertEqual("s2", after[5]["step"]["step_id"])
                        self.assertEqual("step_verifier", after[5]["role"])
                        self.assertEqual(1, final["result"]["budget"]["tool_calls"])
                    else:
                        self.assertEqual("s2" if window == "unknown" else "s3", after[6]["step"]["step_id"])
                    self.assertEqual(original["deadline_at"], final["result"]["budget"]["deadline_at"])
                    self.assertEqual(11 if window == "unknown" else 10, final["result"]["budget"]["logical_calls"])
                    if window == "unknown":
                        self.assertEqual(1, final["result"]["budget"]["unknown_attempts"])
                        self.assertEqual(original["reserved_tokens"], final["result"]["budget"]["reserved_tokens"])
                    stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
                    events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith("data: ")]
                    accepted = [event for event in events if event.get("solver_event_type") == "step_reviewed"]
                    self.assertEqual(3, len(accepted))
                finally:
                    for name in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
                        app.extensions[name].close()

    def test_second_unknown_requires_another_explicit_decision(self):
        self.open_star([requests.Timeout("unknown one"), requests.Timeout("unknown two"),
                        SOLVED, POLISH, ACCEPT],
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8))
        job_id = self.create_job()
        for attempt in range(2):
            job = self.terminal(job_id)
            old_id = job["result"]["solver"]["recovery"]["unknown_calls"][0]["call_id"]
            response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={"retry_call": {
                "call_id": old_id, "new_call_id": str(uuid.uuid4())}}, headers=self.headers())
            self.assertEqual(202, response.status_code, response.get_json())
        self.assertEqual("succeeded", self.terminal(job_id)["status"])
        self.assertEqual(5, len(self.outbound))
        self.assertEqual(2, self.job(job_id)["result"]["budget"]["unknown_attempts"])

    def test_invalid_retry_and_changed_idempotency_body_never_dispatch(self):
        self.open_star([requests.Timeout("unknown"), SOLVED, POLISH, ACCEPT],
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=6, max_http_attempts=6))
        job_id = self.create_job()
        job = self.terminal(job_id)
        old_id = job["result"]["solver"]["recovery"]["unknown_calls"][0]["call_id"]
        for decision in ({}, {"call_id": old_id, "new_call_id": old_id},
                         {"call_id": "another-run", "new_call_id": str(uuid.uuid4())},
                         {"call_id": old_id, "new_call_id": []}):
            response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={"retry_call": decision}, headers=self.headers())
            self.assertEqual(409, response.status_code, response.get_json())
        self.assertEqual(1, len(self.outbound))
        headers = self.headers()
        decision = {"call_id": old_id, "new_call_id": str(uuid.uuid4())}
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={"retry_call": decision}, headers=headers)
        self.assertEqual(202, response.status_code)
        duplicate = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={"retry_call": decision}, headers=headers)
        self.assertEqual(200, duplicate.status_code)
        conflict = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={"retry_call": {
            **decision, "new_call_id": str(uuid.uuid4())}}, headers=headers)
        self.assertEqual(409, conflict.status_code)
        self.assertEqual("succeeded", self.terminal(job_id)["status"])
        self.assertEqual(4, len(self.outbound))

    def test_cancel_during_explicit_retry_preserves_late_unknown_and_stops_math(self):
        import threading
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def paused(_request):
            entered.set()
            release.wait(5)
            return SOLVED
        self.open_star([requests.Timeout("unknown"), paused],
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=6, max_http_attempts=6))
        job_id = self.create_job()
        old_id = self.terminal(job_id)["result"]["solver"]["recovery"]["unknown_calls"][0]["call_id"]
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={"retry_call": {
            "call_id": old_id, "new_call_id": str(uuid.uuid4())}}, headers=self.headers())
        self.assertEqual(202, response.status_code)
        self.assertTrue(entered.wait(5))
        self.cancel(job_id)
        release.set()
        self.wait_for(lambda: self.job(job_id)["result"]["budget"]["provider_known"]["total_tokens"] == 10)
        self.assertEqual("canceled", self.job(job_id)["status"])
        self.assertEqual(2, len(self.outbound))
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers())
        self.assertEqual(409, response.status_code)

    def test_unknown_polish_requires_explicit_retry_and_does_not_repeat_explore(self):
        self.assert_unknown_role([SOLVED, requests.Timeout("unknown polish"), POLISH, ACCEPT], 4)

    def test_unknown_whole_review_does_not_repeat_polish(self):
        self.assert_unknown_role([SOLVED, POLISH, requests.Timeout("unknown review"), ACCEPT], 4)

    def test_unknown_step_review_does_not_repeat_reasoner(self):
        from tests.test_star_product_tools import NEED_PLAN, PLAN, VERDICT
        from tests.test_star_product_planning import STEP, FEATURES
        self.assert_unknown_role([NEED_PLAN, PLAN, STEP, requests.Timeout("unknown step review"),
                                  VERDICT, {"final_response": "2"}, ACCEPT], 7, FEATURES)

    def assert_unknown_role(self, replies, expected_calls, features=None):
        self.open_star(replies, SHOWCASE_STAR_FEATURES=features or {},
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=12, max_http_attempts=12))
        job_id = self.create_job()
        unknown = self.terminal(job_id)["result"]["solver"]["recovery"]["unknown_calls"]
        self.assertEqual(1, len(unknown))
        new_id = str(uuid.uuid4())
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={"retry_call": {
            "call_id": unknown[0]["call_id"], "new_call_id": new_id}}, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(expected_calls, len(self.outbound))
        report = self.client.get(f"/api/agent/jobs/{job_id}/report").get_json()
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertEqual(job["result"]["solver"], report["solver"]["solver"])
        self.assertEqual(job["result"]["solver"], evidence["solver"]["solver"])
        self.assertEqual(job["result"]["budget"], report["report"]["budget"])
        self.assertEqual(job["result"]["budget"], evidence["budget"])
        if unknown[0]["role"] == "whole_solution_verifier":
            self.assertEqual(new_id, job["result"]["verification"]["source"]["call_id"])

    def test_unknown_final_review_reuses_persisted_candidate(self):
        from tests.test_star_product_tools import NEED_PLAN, PLAN, VERDICT
        from tests.test_star_product_planning import STEP, FEATURES
        self.assert_unknown_role([NEED_PLAN, PLAN, STEP, VERDICT, {"final_response": "2"},
                                  requests.Timeout("unknown final review"), ACCEPT], 7, FEATURES)

    def test_rejecting_retried_third_candidate_cannot_reset_final_retry_limit(self):
        from tests.test_star_product_tools import NEED_PLAN, PLAN, VERDICT
        from tests.test_star_product_planning import STEP, FEATURES

        reject = {"verdict": "REJECT", "reason": "Candidate does not resolve the problem"}
        self.open_star([
            NEED_PLAN, PLAN, STEP, VERDICT,
            {"final_response": "candidate one"}, reject,
            {"final_response": "candidate two"}, reject,
            {"final_response": "candidate three"}, requests.Timeout("unknown third review"),
            reject,
            # These replies expose a restored invocation that incorrectly resets the limit.
            {"final_response": "forbidden fourth"}, reject,
            {"final_response": "forbidden fifth"}, ACCEPT,
        ], SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=25, max_http_attempts=25))
        job_id = self.create_job()
        initial = self.terminal(job_id)
        unknown = initial["result"]["solver"]["recovery"]["unknown_calls"]
        self.assertEqual(1, len(unknown))
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={"retry_call": {
            "call_id": unknown[0]["call_id"], "new_call_id": str(uuid.uuid4())}}, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        final = self.terminal(job_id)
        generators = [request for request in self.outbound if request["role"] == "final_generator"]
        reviews = [request for request in self.outbound if request["role"] == "whole_solution_verifier"]
        self.assertEqual(3, len(generators))
        self.assertEqual(4, len(reviews))
        self.assertEqual(11, len(self.outbound))
        self.assertEqual("failed", final["status"])
        self.assertEqual("partial_aborted", final["result"]["solver"]["status"])
        self.assertEqual(initial["result"]["budget"]["deadline_at"], final["result"]["budget"]["deadline_at"])
        self.assertEqual(11, final["result"]["budget"]["http_attempts"])
        self.assertEqual(1, final["result"]["budget"]["unknown_attempts"])
        self.assertEqual(25, final["result"]["budget"]["limits"]["max_model_calls"])
        report = self.report(job_id)
        self.assertIn("final_review_retries_exhausted", report["answer"])
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertEqual(final["result"]["budget"], evidence["budget"])

    def test_retried_third_candidate_can_still_be_accepted_at_generation_limit(self):
        from tests.test_star_product_tools import NEED_PLAN, PLAN, VERDICT
        from tests.test_star_product_planning import STEP, FEATURES

        reject = {"verdict": "REJECT", "reason": "Candidate is incomplete"}
        self.assert_unknown_role([
            NEED_PLAN, PLAN, STEP, VERDICT,
            {"final_response": "candidate one"}, reject,
            {"final_response": "candidate two"}, reject,
            {"final_response": "candidate three"}, requests.Timeout("unknown third review"),
            ACCEPT,
        ], 11, FEATURES)
        self.assertEqual(3, len([request for request in self.outbound
                                if request["role"] == "final_generator"]))
        self.assertEqual(4, len([request for request in self.outbound
                                if request["role"] == "whole_solution_verifier"]))

    def test_unknown_planner_retries_original_action(self):
        from tests.test_star_product_tools import NEED_PLAN, PLAN, VERDICT
        from tests.test_star_product_planning import STEP, FEATURES
        self.assert_unknown_role([NEED_PLAN, requests.Timeout("unknown planner"), PLAN,
                                  STEP, VERDICT, {"final_response": "2"}, ACCEPT], 7, FEATURES)

    def test_unknown_step_reasoner_retries_without_repeating_plan(self):
        from tests.test_star_product_tools import NEED_PLAN, PLAN, VERDICT
        from tests.test_star_product_planning import STEP, FEATURES
        self.assert_unknown_role([NEED_PLAN, PLAN, requests.Timeout("unknown reasoner"),
                                  STEP, VERDICT, {"final_response": "2"}, ACCEPT], 7, FEATURES)

    def test_unknown_final_generator_retries_original_action(self):
        from tests.test_star_product_tools import NEED_PLAN, PLAN, VERDICT
        from tests.test_star_product_planning import STEP, FEATURES
        self.assert_unknown_role([NEED_PLAN, PLAN, STEP, VERDICT, requests.Timeout("unknown final"),
                                  {"final_response": "2"}, ACCEPT], 7, FEATURES)

    def test_concurrent_explicit_decisions_have_one_winner(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def paused(_request):
            entered.set()
            release.wait(5)
            return SOLVED
        self.open_star([requests.Timeout("unknown"), paused, POLISH, ACCEPT],
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=6, max_http_attempts=6))
        job_id = self.create_job()
        old_id = self.terminal(job_id)["result"]["solver"]["recovery"]["unknown_calls"][0]["call_id"]
        barrier = threading.Barrier(2)
        def resume():
            client = self.app.test_client()
            csrf = client.get("/api/check_auth").get_json()["csrf_token"]
            barrier.wait(2)
            return client.post(f"/api/agent/jobs/{job_id}/resume", json={"retry_call": {
                "call_id": old_id, "new_call_id": str(uuid.uuid4())}}, headers={
                    "X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(lambda _: resume(), range(2)))
        self.assertEqual([202, 409], sorted(statuses))
        self.assertTrue(entered.wait(5))
        release.set()
        self.assertEqual("succeeded", self.terminal(job_id)["status"])
        self.assertEqual(4, len(self.outbound))
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        self.assertEqual(1, stream.count("event: resumed"))

    def test_expired_original_deadline_refuses_explicit_retry(self):
        import time
        self.open_star([requests.Timeout("unknown")],
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=6, max_http_attempts=6,
                                                           max_runtime_seconds=1))
        job_id = self.create_job()
        job = self.terminal(job_id)
        old_id = job["result"]["solver"]["recovery"]["unknown_calls"][0]["call_id"]
        time.sleep(1.05)
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={"retry_call": {
            "call_id": old_id, "new_call_id": str(uuid.uuid4())}}, headers=self.headers())
        self.assertEqual(409, response.status_code)
        self.assertEqual(1, len(self.outbound))
