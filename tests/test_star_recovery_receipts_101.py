"""F07/F08: repair receipts survive real exit, concurrent resume and cancellation."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from showcase.flask_app import create_app
from tests.rb06_recovery_worker import config
from tests.star_product_support import StarJobFixture
from tests.test_star_product_python import docker_events
from tests.test_star_rb03_obligations import ACCEPT, DECLARATION, NEED_PLAN, WHOLE_ACCEPT
from tests.test_star_rb06_recovery import SOLUTION

IMAGE = "sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d"


@unittest.skipUnless(os.environ.get("MATHAGENT_TEST_PYTHON_IMAGE") == IMAGE,
                     "requires the fixed validated #101 Docker image")
class RecoveryReceipt101Test(StarJobFixture, unittest.TestCase):
    def open_crashed_job(self, folder):
        """Use a real socket only on loopback; hold the resumed review for races."""
        self.sent = []
        self.review_entered = threading.Event()
        self.release_review = threading.Event()
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
        case = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                wire = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                context = json.loads(wire["messages"][-1]["content"])
                case.sent.append(context)
                role = context["role"]
                content = ("not json" if role == "reasoner"
                           and not context["call_id"].endswith(":repair-1")
                           else json.dumps(replies[role]))
                if role == "step_verifier":
                    case.review_entered.set()
                    if not case.release_review.wait(15):
                        raise AssertionError("review race was not released")
                body = json.dumps({"model": "intern-s2", "choices": [{
                    "message": {"content": content}, "finish_reason": "stop"}],
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
        self.addCleanup(self.release_review.set)
        endpoint = f"http://127.0.0.1:{server.server_port}"
        child = subprocess.run([sys.executable, "-m", "tests.recovery_101_worker",
                                str(folder), endpoint], capture_output=True, timeout=60)
        self.assertEqual(71, child.returncode, child.stderr.decode(errors="replace"))
        job_id = (folder / "job_id").read_text()
        self.assertEqual(["explore", "planner", "reasoner", "reasoner"],
                         [request["role"] for request in self.sent])
        self.assertEqual(self.sent[2]["call_id"] + ":repair-1", self.sent[3]["call_id"])
        self.assertIn("repair_instruction", self.sent[3])
        self.app = create_app(config(folder, endpoint, "star_reference"))
        for name in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            self.addCleanup(self.app.extensions[name].close)
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
        before = self.job(job_id)
        self.assertEqual("failed", before["status"])
        self.assertEqual("safe", before["result"]["solver"]["recovery"]["status"])
        original = before["result"]["budget"]
        self.assertEqual((4, 4, 1, 0), tuple(original[key] for key in
                         ("logical_calls", "http_attempts", "tool_calls", "unknown_attempts")))
        return job_id, original

    def post(self, job_id, operation, headers, body=None):
        with self.app.test_client() as client:
            csrf = client.get("/api/check_auth").get_json()["csrf_token"]
            return client.post(f"/api/agent/jobs/{job_id}/{operation}",
                               json=body or {}, headers={**headers, "X-CSRF-Token": csrf})

    def events(self, job_id):
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        return [json.loads(line[6:]) for line in stream.splitlines() if line.startswith("data: ")]

    def assert_original_budget(self, original, budget, calls):
        for key in ("deadline_at", "limits", "reserved_tokens"):
            self.assertEqual(original[key], budget[key], key)
        self.assertEqual((calls, calls, 1, 0), tuple(budget[key] for key in
                         ("logical_calls", "http_attempts", "tool_calls", "unknown_attempts")))
        self.assertEqual(calls * 10, budget["provider_known"]["total_tokens"])

    def assert_single_container(self, job_id):
        events = docker_events(job_id)
        self.assertEqual(1, sum(event.get("Action") == "create" for event in events))
        self.assertEqual(1, sum(event.get("Action") == "destroy" for event in events))

    def test_repaired_receipt_survives_exit_and_two_resumers_without_duplicate_actions(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        job_id, original = self.open_crashed_job(Path(directory))
        headers = [self.headers(), self.headers()]
        barrier = threading.Barrier(2)

        def resume(index):
            barrier.wait(timeout=5)
            return self.post(job_id, "resume", headers[index])

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(resume, range(2)))
        self.assertEqual([202, 409], sorted(result.status_code for result in results))
        winner = next(i for i, response in enumerate(results) if response.status_code == 202)
        duplicate = self.post(job_id, "resume", headers[winner])
        self.assertEqual(200, duplicate.status_code)
        self.assertTrue(duplicate.get_json()["existing"])
        self.assertEqual(job_id, duplicate.get_json()["job_id"])
        conflict = self.post(job_id, "resume", headers[winner], {"retry_call": {}})
        self.assertEqual(409, conflict.status_code)
        self.assertTrue(self.review_entered.wait(5))
        self.release_review.set()
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual(SOLUTION, final["result"]["final_response"])
        self.assert_original_budget(original, final["result"]["budget"], 7)
        receipt = self.sent[4]["report"]["tool_receipts"][0]
        self.assertEqual(("391\n", IMAGE, True),
                         (receipt["output"], receipt["image"], receipt["cleanup_verified"]))
        events = self.events(job_id)
        for kind in ("resumed", "tool_receipt", "step_reviewed"):
            self.assertEqual(1, sum(event.get("solver_event_type", event["type"]) == kind
                                    for event in events), kind)
        self.assertEqual(1, len(final["result"]["solver"]["recovery"]["protocol_failures"]))
        self.assertEqual("same_artifact", self.report(job_id)["checks"]["binding"])
        self.assert_single_container(job_id)

    def test_cancel_wins_while_resumed_review_is_inflight_without_reviving_progress(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        job_id, original = self.open_crashed_job(Path(directory))
        self.assertEqual(202, self.post(job_id, "resume", self.headers()).status_code)
        self.assertTrue(self.review_entered.wait(5))
        canceled = self.cancel(job_id)
        self.assertEqual("canceled", canceled["status"])
        rejected = self.post(job_id, "resume", self.headers())
        self.assertEqual(409, rejected.status_code)
        self.release_review.set()
        self.wait_for(lambda: self.job(job_id)["result"]["budget"]["provider_known"].get(
            "total_tokens") == 50)
        final = self.job(job_id)
        self.assertEqual("canceled", final["status"])
        self.assert_original_budget(original, final["result"]["budget"], 5)
        self.assertEqual(["explore", "planner", "reasoner", "reasoner", "step_verifier"],
                         [request["role"] for request in self.sent])
        events = self.events(job_id)
        self.assertEqual([], [event for event in events
                              if event.get("solver_event_type") == "step_reviewed"])
        self.assertEqual(1, sum(event.get("solver_event_type") == "tool_receipt"
                                for event in events))
        self.assert_single_container(job_id)


if __name__ == "__main__":
    unittest.main()
