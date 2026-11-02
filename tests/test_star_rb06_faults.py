"""E3 public fault combinations after finite computation and numeric review."""

import json
import threading
import time
import unittest
import uuid
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import requests

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.run_budget import RunBudgetLimits, current_budget
from showcase.tools import ToolRegistry
from tests.star_product_support import StarJobFixture
from tests.test_star_rb03_obligations import ACCEPT, DECLARATION, NEED_PLAN, NOT_FOUND, WHOLE_ACCEPT

PLAN = {"version": 1, "steps": [{"step_id": "sum", "title": "Sum", "objective": "Compute 1+1"}]}
STEP = {"argument": "1+1=2", "blocked": False, "claims": [{"statement": "1+1=2",
    "label": "easy-verify", "tool_request": {"tool": "polynomial_check", "arguments": {},
                                                "scope": "finite_computation"}}]}
REVIEW = {**ACCEPT, "answer_claim": {**DECLARATION, "claim_type": "numerical_evaluation"}}
FINAL = {"final_response": "1+1=2 by addition."}


class RobustFaultTest(StarJobFixture, unittest.TestCase):
    def open_numeric(self, tail, *, limits=None, step=STEP):
        """Replace provider HTTP only; Registry records its actual S3 Run identity."""
        self.tools = []
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda _: self.tools.append(current_budget().run_id) or 2)
        self.open_star([NEED_PLAN, PLAN, step, *tail],
            SHOWCASE_STAR_REGISTRY=registry,
            SHOWCASE_STAR_FEATURES={"skills": True, "local_code_tool": True,
                                   "final_generation": True, "final_solution_review": True},
            SHOWCASE_STAR_BUDGET=limits or RunBudgetLimits(max_model_calls=10, max_http_attempts=10))

    def test_unknown_whole_review_keeps_completed_numeric_actions_and_reservation(self):
        self.open_numeric([REVIEW, FINAL, requests.ReadTimeout("in flight"), WHOLE_ACCEPT])
        job_id = self.create_job()
        failed = self.terminal(job_id)
        old = failed["result"]["budget"]
        call = failed["result"]["solver"]["recovery"]["unknown_calls"][0]["call_id"]
        self.assertEqual("unknown", self.report(job_id)["semantics"]["transport"])
        for path in (f"/api/agent/jobs/{job_id}/resume", f"/api/runs/{job_id}/resume"):
            self.assertEqual(409, self.client.post(path, json={}, headers=self.headers()).status_code)
        self.assertEqual(6, self.post.call_count)
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", headers=self.headers(),
            json={"retry_call": {"call_id": call, "new_call_id": str(uuid.uuid4())}})
        self.assertEqual(202, response.status_code, response.get_json())
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final)
        budget = final["result"]["budget"]
        self.assertEqual(old["deadline_at"], budget["deadline_at"])
        self.assertEqual(old["reserved_tokens"], budget["reserved_tokens"])
        self.assertGreater(budget["reserved_tokens"], 0)
        self.assertEqual((7, 7, 1, 1), tuple(budget[k] for k in (
            "logical_calls", "http_attempts", "tool_calls", "unknown_attempts")))
        self.assertEqual([job_id], self.tools)
        self.assertEqual(["explore", "planner", "reasoner", "step_verifier", "final_generator",
                          "whole_solution_verifier", "whole_solution_verifier"],
                         [r["role"] for r in self.outbound])
        receipt = self.outbound[3]["report"]["tool_receipts"][0]
        self.assertEqual("not_compared", receipt["comparison_status"])
        self.assertEqual("easy-verify", self.outbound[3]["report"]["claims"][0]["label"])
        self.assertEqual("same_artifact", self.report(job_id)["semantics"]["binding"])
        self.client.get(f"/api/runs/{job_id}/evidence")
        self.assertEqual(7, self.post.call_count)

    def test_numeric_tool_model_http_and_token_admission_remain_independent(self):
        cases = [
            (RunBudgetLimits(max_model_calls=3, max_http_attempts=10), 3, 1),
            (RunBudgetLimits(max_model_calls=10, max_http_attempts=3), 3, 1),
            (RunBudgetLimits(max_tokens=1), 0, 0),
        ]
        for limits, calls, tools in cases:
            with self.subTest(limits=limits):
                self.open_numeric([REVIEW, FINAL, WHOLE_ACCEPT], limits=limits)
                job_id = self.create_job()
                job = self.terminal(job_id)
                self.assertEqual("failed", job["status"], job)
                self.assertEqual(calls, self.post.call_count)
                self.assertEqual(tools, len(self.tools))
                report = self.report(job_id)
                self.assertEqual(calls, report["budget"]["http_attempts"])
                self.assertEqual(tools, report["budget"]["tool_calls"])
                self.assertNotEqual("accepted", report["semantics"]["whole_review"])

    def test_zero_tool_quota_allows_numeric_reasoning_and_whole_review(self):
        self.open_numeric([REVIEW, FINAL, WHOLE_ACCEPT], limits=RunBudgetLimits(max_tool_calls=0))
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(FINAL["final_response"], job["result"]["final_response"])
        self.assertEqual([], self.tools)
        report = self.report(job_id)
        self.assertEqual(6, report["budget"]["http_attempts"])
        self.assertEqual(0, report["budget"]["tool_calls"])
        self.assertEqual("accepted", report["semantics"]["whole_review"])
        self.assertEqual("same_artifact", report["semantics"]["binding"])
        receipt = self.outbound[3]["report"]["tool_receipts"][0]
        self.assertFalse(receipt["executed"])
        self.assertEqual("tool_call_budget_exhausted", receipt["reason"])

    def test_cancel_after_numeric_review_never_binds_late_final_text(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def delayed(_):
            entered.set()
            release.wait(5)
            return FINAL

        self.open_numeric([REVIEW, delayed])
        job_id = self.create_job()
        self.assertTrue(entered.wait(5))
        self.cancel(job_id)
        original = self.report(job_id)["budget"]
        release.set()
        self.wait_for(lambda: self.report(job_id)["budget"]["provider_known"]["total_tokens"] == 50)
        self.assertEqual("canceled", self.job(job_id)["status"])
        self.assertEqual([job_id], self.tools)
        self.assertEqual(5, self.post.call_count)
        report = self.report(job_id)
        self.assertEqual(original["deadline_at"], report["budget"]["deadline_at"])
        self.assertNotEqual("accepted", report["semantics"]["whole_review"])
        self.assertEqual(409, self.client.post(f"/api/agent/jobs/{job_id}/resume",
            json={}, headers=self.headers()).status_code)

    def test_sharp_obligation_still_challenges_after_numeric_computation(self):
        step = deepcopy(STEP)
        step["claims"][0]["statement"] = "The sharp lower bound of x² is 0."
        review = {**ACCEPT, "answer_claim": {**DECLARATION, "claim_type": "sharp_bound"}}
        self.open_numeric([review, NOT_FOUND], step=step,
                          limits=RunBudgetLimits(max_model_calls=5, max_http_attempts=5))
        job_id = self.create_job()
        self.assertEqual("failed", self.terminal(job_id)["status"])
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith("data: ")]
        reviewed = next(e for e in events if e.get("solver_event_type") == "step_reviewed")
        self.assertEqual("CHALLENGE", reviewed["verdict"], "RB06 applicable obligation")
        self.assertEqual([job_id], self.tools)

    def test_public_http_deadline_stops_waiting_and_only_late_usage_can_settle(self):
        """Real HTTP delayed headers cannot hide a Run deadline or trigger resend."""
        sent = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                sent.append(self.rfile.read(int(self.headers["Content-Length"])))
                time.sleep(1.2)
                body = json.dumps({"choices": [{"message": {"content": json.dumps(NEED_PLAN)},
                    "finish_reason": "stop"}], "usage": {"total_tokens": 10,
                    "prompt_tokens": 7, "completion_tokens": 3}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        real_post = requests.post
        with patch.dict("os.environ", {"INTERN_API_KEY": "loopback-only"}):
            provider = InternChatClient(retry=1, timeout=3)
        provider.api_base = f"http://127.0.0.1:{server.server_port}"
        self.open_star([], SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_runtime_seconds=.3),
                       SHOWCASE_STAR_ADAPTER=InternModelAdapter(provider, max_tokens=256))
        with patch("llm_client.requests.post", real_post):
            started = time.monotonic()
            job_id = self.create_job()
            final = self.terminal(job_id)
            self.assertLess(time.monotonic() - started, .9, "RB06 hard deadline")
            self.assertEqual("failed", final["status"])
            report = self.report(job_id)
            self.assertEqual("unknown", report["semantics"]["transport"])
            self.assertEqual(1, report["budget"]["unknown_attempts"])
            self.assertGreater(report["budget"]["reserved_tokens"], 0)
            self.assertEqual(409, self.client.post(f"/api/agent/jobs/{job_id}/resume",
                json={}, headers=self.headers()).status_code)
            self.wait_for(lambda: self.report(job_id)["budget"]["provider_known"]["total_tokens"] == 10)
            self.assertEqual(1, len(sent))
            self.assertEqual("failed", self.job(job_id)["status"])
            self.assertEqual("not_reviewed", self.report(job_id)["semantics"]["whole_review"])
