"""E3 composition through authenticated Job/Run with real loopback and Docker."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from showcase.flask_app import create_app
from tests.rb06_recovery_worker import config
from tests.star_product_support import StarJobFixture
from tests.test_star_product_python import docker_events
from tests.test_star_rb03_obligations import ACCEPT, DECLARATION, NEED_PLAN, WHOLE_ACCEPT

IMAGE = os.environ.get("MATHAGENT_TEST_PYTHON_IMAGE")
SOLUTION = "17*23=17*(20+3)=340+51=391."


@unittest.skipUnless(IMAGE, "requires the validated exact local Docker image")
class RobustRecoveryTest(StarJobFixture, unittest.TestCase):
    def test_real_receipt_exit_resumes_numeric_review_once_with_original_ledger(self):
        """New comparison/obligation/transport/state semantics survive one crash."""
        self._run_receipt_recovery("star_limited")

    def test_reference_receipt_exit_resumes_same_job_through_final_review_and_binding(self):
        """The complete Reference preset preserves the same recovery contract."""
        self._run_receipt_recovery("star_reference")

    def _run_receipt_recovery(self, solver_mode):
        sent = []
        replies = {
            "explore": NEED_PLAN,
            "planner": {"version": 1, "steps": [{"step_id": "multiply", "title": "Multiply",
                "objective": "Compute and explain 17*23"}]},
            "reasoner": {"argument": SOLUTION, "blocked": False, "claims": [{
                "statement": "17*23=391", "label": "easy-verify", "tool_request": {
                    "tool": "python_math", "arguments": {"code": "print(17*23)"},
                    "scope": "finite_computation"}}]},
            "step_verifier": {**ACCEPT, "answer_claim": {
                **DECLARATION, "claim_type": "numerical_evaluation"}},
            "final_generator": {"final_response": SOLUTION},
            "whole_solution_verifier": WHOLE_ACCEPT,
        }

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                wire = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                context = json.loads(wire["messages"][-1]["content"])
                sent.append(context)
                value = replies.get(context["role"], {})
                body = json.dumps({"model": "intern-s2", "choices": [{
                    "message": {"content": json.dumps(value)}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3,
                              "total_tokens": 10}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        endpoint = f"http://127.0.0.1:{server.server_port}"
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            child = subprocess.run([sys.executable, "-m", "tests.rb06_recovery_worker",
                directory, endpoint, solver_mode], capture_output=True, timeout=60)
            self.assertEqual(71, child.returncode, child.stderr.decode(errors="replace"))
            job_id = (folder / "job_id").read_text()
            self.assertEqual(["explore", "planner", "reasoner"], [r["role"] for r in sent])
            self.app = create_app(config(folder, endpoint, solver_mode))
            try:
                self.client = self.app.test_client()
                self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
                before = self.job(job_id)
                self.assertEqual("failed", before["status"])
                original = before["result"]["budget"]
                self.assertEqual(1, original["tool_calls"])
                response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={},
                                            headers=self.headers())
                self.assertEqual(202, response.status_code, response.get_json())
                final = self.terminal(job_id)
                self.assertEqual("succeeded", final["status"], final)
                self.assertEqual("fault_injection", final["result"]["evidence_kind"])
                self.assertEqual(solver_mode, final["result"]["execution_mode"])
                self.assertEqual(SOLUTION, final["result"]["final_response"])
                self.assertEqual(["explore", "planner", "reasoner", "step_verifier",
                    "final_generator", "whole_solution_verifier"], [r["role"] for r in sent])
                receipt = sent[3]["report"]["tool_receipts"][0]
                self.assertEqual("391\n", receipt["output"], receipt)
                self.assertEqual("not_compared", receipt["comparison_status"])
                self.assertFalse(receipt["assertion_matched"])
                self.assertEqual("easy-verify", sent[3]["report"]["claims"][0]["label"])
                self.assertTrue(receipt["cleanup_verified"])
                self.assertEqual(IMAGE, receipt["image"])
                budget = final["result"]["budget"]
                self.assertEqual(original["deadline_at"], budget["deadline_at"])
                self.assertEqual((6, 6, 1, 0), tuple(budget[k] for k in (
                    "logical_calls", "http_attempts", "tool_calls", "unknown_attempts")))
                self.assertEqual(60, budget["provider_known"]["total_tokens"])
                report = self.report(job_id)
                evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
                self.assertEqual(report["semantics"], evidence["semantics"])
                self.assertEqual("accepted", report["semantics"]["whole_review"])
                self.assertEqual("same_artifact", report["semantics"]["binding"])
                self.assertEqual("not_verified", report["semantics"]["formal_verification"])
                attempts = report["request_attempts"]
                self.assertEqual(6, len(attempts))
                for attempt in attempts:
                    self.assertTrue(attempt["request_purpose"])
                    self.assertTrue(attempt["solver_call_id"])
                    self.assertIsNotNone(attempt["response_headers_seconds"])
                    self.assertIsNotNone(attempt["completion_seconds"])
                    self.assertIsNone(attempt["first_event_seconds"])
                    self.assertIsNone(attempt["cost"])
                    self.assertEqual(10, attempt["usage"]["total_tokens"])
                events = docker_events(job_id)
                self.assertEqual(1, sum(e.get("Action") == "create" for e in events))
                self.assertEqual(1, sum(e.get("Action") == "destroy" for e in events))
                self.client.get(f"/api/agent/jobs/{job_id}/events").get_data()
                self.client.get(f"/api/runs/{job_id}")
                self.assertEqual(6, len(sent))
            finally:
                for name in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
                    self.app.extensions[name].close()
