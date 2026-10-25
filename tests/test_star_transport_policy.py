"""Transport safety at the public Job boundary and production HTTP adapter."""
import unittest
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import requests

from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture
from showcase.run_budget import RunBudgetLimits


class StarTransportPolicyTest(StarJobFixture, unittest.TestCase):
    def check_rejected_retry_after(self, value):
        self.open_star([], retry=3)
        response = requests.Response()
        response.status_code = 429
        if value is not None:
            response.headers["Retry-After"] = value
        self.post.side_effect = None
        self.post.return_value = response
        job_id = self.create_job()
        result = self.terminal(job_id)
        self.assertEqual("failed", result["status"])
        self.assertEqual(1, self.post.call_count)
        self.assertGreater(result["result"]["budget"]["reserved_tokens"], 0)

    def test_retry_after_missing(self):
        self.check_rejected_retry_after(None)

    def test_retry_after_invalid(self):
        self.check_rejected_retry_after("invalid")

    def test_retry_after_negative(self):
        self.check_rejected_retry_after("-1")

    def test_retry_after_nan(self):
        self.check_rejected_retry_after("NaN")

    def test_retry_after_infinity(self):
        self.check_rejected_retry_after("Infinity")

    def test_retry_after_http_date(self):
        import time
        from email.utils import formatdate
        self.open_star([SOLVED, POLISH, ACCEPT], retry=3,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_http_attempts=8))
        respond = self.post.side_effect
        response = requests.Response()
        response.status_code = 429
        response.headers["Retry-After"] = formatdate(time.time() + 2, usegmt=True)
        calls = []
        def limited(*args, **kwargs):
            calls.append(kwargs)
            return response if len(calls) == 1 else respond(*args, **kwargs)
        self.post.side_effect = limited
        job_id = self.create_job()
        result = self.terminal(job_id)
        self.assertEqual("succeeded", result["status"], result)
        self.assertEqual(4, len(calls))
        self.assertEqual("1+1=2", result["result"]["final_response"])

    def test_retry_after_exceeds_original_deadline(self):
        self.check_rejected_retry_after("999999")

    def test_real_http_429_retry_after_then_answer(self):
        self.open_star([], retry=3, SHOWCASE_STAR_BUDGET=RunBudgetLimits(
            max_model_calls=8, max_http_attempts=8))

        self.post.side_effect = lambda url, **kwargs: requests.Session().post(url, **kwargs)
        received = []
        replies = [SOLVED, POLISH, ACCEPT]

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                if len(received) == 1:
                    self.send_response(429)
                    self.send_header("Retry-After", "0")
                    self.end_headers()
                    return
                body = json.dumps({"choices": [{"finish_reason": "stop", "message": {
                    "content": json.dumps(replies.pop(0))}}], "model": "intern-s2",
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with patch("llm_client.requests.post", wraps=requests.post) as outgoing:
            # Point the injected production client at loopback, not a paid API.
            with patch("llm_client.DEFAULT_API_BASE", f"http://127.0.0.1:{server.server_port}"):
                # The fixture client was constructed already; select it from the
                # bound post's request URL without replacing HTTP execution.
                original = requests.sessions.Session.request
                def local(session, method, url, **kwargs):
                    return original(session, method, f"http://127.0.0.1:{server.server_port}", **kwargs)
                with patch("requests.sessions.Session.request", new=local):
                    job_id = self.create_job()
                    result = self.terminal(job_id)
        self.assertEqual("succeeded", result["status"], result)
        self.assertEqual(4, len(received))
        self.assertEqual("1+1=2", result["result"]["final_response"])
        self.assertEqual(4, outgoing.call_count)
        attempts = result["result"]["request_attempts"]
        self.assertEqual(4, len({item["attempt_id"] for item in attempts}))
        self.assertEqual(attempts[0]["logical_call_id"], attempts[1]["logical_call_id"])

    def test_real_connection_refused_is_bounded(self):
        import socket
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.open_star([], retry=5, SHOWCASE_STAR_BUDGET=RunBudgetLimits(
            max_model_calls=8, max_http_attempts=8))
        def refused(url, **kwargs):
            kwargs["timeout"] = .1
            return requests.Session().post(f"http://127.0.0.1:{port}", **kwargs)
        self.post.side_effect = refused
        job_id = self.create_job()
        result = self.terminal(job_id)
        self.assertEqual("failed", result["status"])
        self.assertEqual(3, self.post.call_count)
        self.assertEqual(0, result["result"]["budget"]["reserved_tokens"])


    def test_read_timeout_is_not_automatically_resent(self):
        self.open_star([requests.ReadTimeout("unknown"), SOLVED, POLISH, ACCEPT], retry=3,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8))
        job_id = self.create_job()
        result = self.terminal(job_id)
        self.assertEqual("failed", result["status"], result)
        self.assertEqual(1, len(self.outbound))
        self.assertEqual("needs_review", result["result"]["solver"]["recovery"]["status"])
        self.assertGreater(result["result"]["budget"]["reserved_tokens"], 0)

    def test_connect_timeout_retries_then_delivers_actual_answer(self):
        self.open_star([requests.ConnectTimeout("not submitted"), SOLVED, POLISH, ACCEPT], retry=3,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8))
        job_id = self.create_job()
        result = self.terminal(job_id)
        self.assertEqual("succeeded", result["status"], result)
        self.assertEqual(["explore", "explore", "explore_polish", "whole_solution_verifier"],
                         [item["role"] for item in self.outbound])
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertEqual(4, evidence["budget"]["http_attempts"])
        self.assertEqual(0, evidence["budget"]["unknown_attempts"])
        self.assertIn("1+1=2", str(result))

    def test_safe_failures_stop_after_three_total_attempts(self):
        self.open_star([requests.ConnectTimeout("not submitted") for _ in range(5)], retry=5,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8))
        job_id = self.create_job()
        result = self.terminal(job_id)
        self.assertEqual("failed", result["status"])
        self.assertEqual(3, len(self.outbound))
        self.assertEqual(0, result["result"]["budget"]["reserved_tokens"])

    def test_sent_connection_failure_is_unknown_without_resend(self):
        self.open_star([requests.ConnectionError("response interrupted"), SOLVED], retry=3)
        job_id = self.create_job()
        result = self.terminal(job_id)
        self.assertEqual("failed", result["status"])
        self.assertEqual(1, len(self.outbound))
        self.assertGreater(result["result"]["budget"]["reserved_tokens"], 0)

