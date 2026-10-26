"""Transport safety at the public Job boundary and production HTTP adapter."""
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import requests

from llm_client import InternChatClient
from showcase.adapters import AdapterError, InternModelAdapter, InternStreamAdapter
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture


class StarTransportPolicyTest(StarJobFixture, unittest.TestCase):
    def local_server(self, handler):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}"

    def test_stream_and_nonstream_send_same_effective_model_configuration(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                received.append(payload)
                streaming = payload.get("stream", False)
                thinking = payload.get("thinking_mode", "<missing>")
                if sum(
                    item.get("stream", False) == streaming
                    and item.get("thinking_mode", "<missing>") == thinking
                    for item in received
                ) == 1:
                    self.send_response(429)
                    self.send_header("Retry-After", "0")
                    self.end_headers()
                    return
                if streaming:
                    body = (
                        b'data: {"model":"intern-s2","choices":[{"delta":{"content":"ok"},'
                        b'"finish_reason":"stop"}],"usage":{"prompt_tokens":1,'
                        b'"completion_tokens":1,"total_tokens":2}}\n\n'
                        b"data: [DONE]\n\n"
                    )
                    content_type = "text/event-stream"
                else:
                    body = json.dumps({"model": "intern-s2", "choices": [{
                        "message": {"content": "ok"}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                                  "total_tokens": 2}}).encode()
                    content_type = "application/json"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        adapter_options = {"temperature": 0.4, "max_tokens": 8192}
        messages = [{"role": "user", "content": "Return ok"}]

        for thinking_mode in (True, None):
            client = InternChatClient(timeout=180, retry=2, thinking_mode=thinking_mode)
            if thinking_mode is None:
                client.thinking_mode = None
            expected_model = client.model
            client.api_base = f"http://127.0.0.1:{server.server_port}"
            for run_id, adapter, streaming in (
                (f"nonstream-{thinking_mode}", InternModelAdapter(client, **adapter_options), False),
                (f"stream-{thinking_mode}", InternStreamAdapter(client, **adapter_options), True),
            ):
                ledger = RunBudgetLedger()
                budget = ledger.ensure(run_id, RunBudgetLimits(max_runtime_seconds=10))
                try:
                    with bind_budget(budget):
                        if streaming:
                            chunks = list(adapter.stream_complete(messages, metadata={"role": "test"}))
                            self.assertEqual("ok", chunks[-1]["text"])
                            request_attempts = chunks[-1]["attempts"]
                        else:
                            response = adapter.complete(messages, metadata={"role": "test"})
                            self.assertEqual("ok", response.text)
                            request_attempts = response.request_attempts
                    self.assertEqual(2, len(request_attempts))
                    self.assertTrue(all(item["response_headers_seconds"] is not None
                                        for item in request_attempts))
                    self.assertTrue(all(item["requested_model"] == expected_model
                                        and item["temperature"] == 0.4
                                        and item["max_tokens"] == 8192
                                        and item["retry_limit"] == 2
                                        and 0 < item["effective_timeout_seconds"] <= 180
                                        and item["requests_timeout_seconds"] == 180
                                        and item["provider_stream"] is streaming
                                        and item["requests_stream"] is True
                                        for item in request_attempts), request_attempts)
                    complete_attempt = request_attempts[-1]
                    self.assertIsNotNone(complete_attempt["response_headers_seconds"])
                    self.assertIsNotNone(complete_attempt["first_byte_seconds"])
                    self.assertIsNotNone(complete_attempt["completion_seconds"])
                    self.assertEqual(streaming, complete_attempt["first_content_seconds"] is not None)
                    if not streaming:
                        self.assertIsNone(complete_attempt["first_reasoning_seconds"])
                    self.assertEqual(streaming, complete_attempt["first_event_seconds"] is not None)
                finally:
                    ledger.close()

            ordinary = next(item for item in received if not item.get("stream", False)
                            and item.get("thinking_mode", "<missing>") == (thinking_mode if thinking_mode is not None else "<missing>"))
            streamed = next(item for item in received if item.get("stream", False)
                            and item.get("thinking_mode", "<missing>") == (thinking_mode if thinking_mode is not None else "<missing>"))
            for key in ("model", "temperature", "max_tokens", "thinking_mode"):
                self.assertEqual(ordinary.get(key), streamed.get(key), key)
            if thinking_mode is None:
                self.assertNotIn("thinking_mode", ordinary)
                self.assertNotIn("thinking_mode", streamed)
            self.assertEqual(2, sum(not item.get("stream", False)
                                    and item.get("thinking_mode", "<missing>") == (thinking_mode if thinking_mode is not None else "<missing>")
                                    for item in received))
            self.assertEqual(2, sum(item.get("stream", False)
                                    and item.get("thinking_mode", "<missing>") == (thinking_mode if thinking_mode is not None else "<missing>")
                                    for item in received))

    def test_stream_lifecycle_reports_reasoning_before_visible_content(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                time.sleep(0.02)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for payload in (
                    'data: {"choices":[{"delta":{"reasoning_content":"r"}}]}\n\n',
                    'data: {"choices":[{"delta":{"content":"answer"}}]}\n\n',
                    'data: {"model":"intern-s2","choices":[{"delta":{},'
                    '"finish_reason":"stop"}],"usage":{"prompt_tokens":2,'
                    '"completion_tokens":3,"total_tokens":5}}\n\n',
                    "data: [DONE]\n\n",
                ):
                    self.wfile.write(payload.encode())
                    self.wfile.flush()
                    time.sleep(0.02)

        client = InternChatClient(timeout=2, retry=1, thinking_mode=True)
        client.api_base = self.local_server(Handler)
        adapter = InternStreamAdapter(client, temperature=0.3, max_tokens=256)
        ledger = RunBudgetLedger()
        budget = ledger.ensure("timed", RunBudgetLimits(max_runtime_seconds=5))
        self.addCleanup(ledger.close)
        with bind_budget(budget):
            chunks = list(adapter.stream_complete(
                [{"role": "user", "content": "Return an answer"}],
                metadata={"role": "solver"},
            ))

        attempt = chunks[-1]["attempts"][0]
        self.assertEqual("answer", chunks[-1]["text"])
        self.assertLessEqual(attempt["response_headers_seconds"], attempt["first_byte_seconds"])
        self.assertLessEqual(attempt["first_byte_seconds"], attempt["first_event_seconds"])
        self.assertLess(attempt["first_reasoning_seconds"], attempt["first_content_seconds"])
        self.assertLessEqual(attempt["first_content_seconds"], attempt["completion_seconds"])
        self.assertEqual(1, attempt["reasoning_chars"])
        self.assertEqual(4, attempt["event_count"])
        self.assertEqual(6, attempt["content_bytes"])
        self.assertEqual("solver", attempt["request_purpose"])
        self.assertEqual(0.3, attempt["temperature"])
        self.assertEqual(256, attempt["max_tokens"])

    def test_slow_trickled_bytes_without_newline_hit_logical_deadline(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", "80")
                self.end_headers()
                for _ in range(80):
                    try:
                        self.wfile.write(b"x")
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    time.sleep(0.01)

        client = InternChatClient(timeout=2, retry=3, thinking_mode=True)
        client.api_base = self.local_server(Handler)
        adapter = InternStreamAdapter(client, max_tokens=256)
        ledger = RunBudgetLedger()
        budget = ledger.ensure("trickle", RunBudgetLimits(max_runtime_seconds=5))
        self.addCleanup(ledger.close)
        started = time.monotonic()
        with bind_budget(budget), self.assertRaises(AdapterError) as raised:
            list(adapter.stream_complete(
                [{"role": "user", "content": "Return an answer"}],
                metadata={"role": "solver", "timeout_seconds": 0.12},
            ))
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual("timeout", raised.exception.category)
        self.assertEqual(1, len(raised.exception.request_attempts))
        self.assertEqual(1, budget.snapshot()["http_attempts"])
        self.assertEqual(1, budget.snapshot()["unknown_attempts"])
        self.assertGreater(budget.snapshot()["reserved_tokens"], 0)

    def test_late_complete_usage_settles_the_original_unknown_reservation(self):
        response_sent = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                time.sleep(0.18)
                body = (
                    b'data: {"model":"intern-s2","choices":[{"delta":{"content":"late"},'
                    b'"finish_reason":"stop"}],"usage":{"prompt_tokens":2,'
                    b'"completion_tokens":3,"total_tokens":5}}\n\n'
                    b"data: [DONE]\n\n"
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
                response_sent.set()

        client = InternChatClient(timeout=2, retry=3, thinking_mode=True)
        client.api_base = self.local_server(Handler)
        adapter = InternStreamAdapter(client, max_tokens=256)
        ledger = RunBudgetLedger()
        budget = ledger.ensure("late", RunBudgetLimits(max_runtime_seconds=0.08))
        self.addCleanup(ledger.close)
        with bind_budget(budget), self.assertRaises(AdapterError) as raised:
            list(adapter.stream_complete(
                [{"role": "user", "content": "Return an answer"}],
                metadata={"role": "solver", "timeout_seconds": 0.5},
            ))
        self.assertEqual("timeout", raised.exception.category)
        self.assertLessEqual(raised.exception.request_attempts[0]["effective_timeout_seconds"], 0.08)
        self.assertEqual(1, budget.snapshot()["unknown_attempts"])
        self.assertTrue(response_sent.wait(1))
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and budget.snapshot()["unknown_attempts"]:
            time.sleep(0.01)
        self.assertEqual(0, budget.snapshot()["unknown_attempts"])
        self.assertEqual(0, budget.snapshot()["reserved_tokens"])
        settled = budget.ledger.attempts("late")[0]
        self.assertEqual(5, settled["usage"]["total_tokens"])
        self.assertIsNone(settled["first_content_seconds"])

    def test_idle_pause_after_first_event_is_unknown_and_never_retried(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(b'data: {"choices":[{"delta":{"content":"x"}}]}\n\n')
                self.wfile.flush()
                time.sleep(0.3)

        client = InternChatClient(timeout=2, retry=3, thinking_mode=True)
        client.api_base = self.local_server(Handler)
        adapter = InternStreamAdapter(client, max_tokens=256)
        ledger = RunBudgetLedger()
        budget = ledger.ensure("idle", RunBudgetLimits(max_runtime_seconds=5))
        self.addCleanup(ledger.close)
        with bind_budget(budget), self.assertRaises(AdapterError) as raised:
            list(adapter.stream_complete(
                [{"role": "user", "content": "Return an answer"}],
                metadata={"role": "solver", "timeout_seconds": 0.08},
            ))
        self.assertEqual("timeout", raised.exception.category)
        self.assertEqual(1, budget.snapshot()["http_attempts"])
        self.assertEqual(1, budget.snapshot()["unknown_attempts"])
        self.assertIsNone(raised.exception.request_attempts[0]["completion_seconds"])

    def test_abrupt_eof_without_done_is_unknown_and_never_retried(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", "1000")
                self.end_headers()
                try:
                    self.wfile.write(b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n')
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

        client = InternChatClient(timeout=2, retry=3, thinking_mode=True)
        client.api_base = self.local_server(Handler)
        adapter = InternStreamAdapter(client, max_tokens=256)
        ledger = RunBudgetLedger()
        budget = ledger.ensure("eof", RunBudgetLimits(max_runtime_seconds=5))
        self.addCleanup(ledger.close)
        with bind_budget(budget), self.assertRaises(AdapterError) as raised:
            list(adapter.stream_complete(
                [{"role": "user", "content": "Return an answer"}],
                metadata={"role": "solver"},
            ))
        self.assertEqual("connectivity", raised.exception.category)
        self.assertEqual(1, budget.snapshot()["http_attempts"])
        self.assertEqual(1, budget.snapshot()["unknown_attempts"])

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

    def test_default_production_job_sends_180_seconds(self):
        self.open_star([SOLVED, POLISH, ACCEPT], SHOWCASE_STAR_ADAPTER=None)
        job_id = self.create_job()
        result = self.terminal(job_id)
        self.assertEqual("succeeded", result["status"], result)
        self.assertEqual(180, self.post.call_args_list[0].kwargs["timeout"])
        self.assertEqual("1+1=2", result["result"]["final_response"])
        self.assertEqual(3, self.post.call_count)

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


    def test_suppressed_old_connect_failure_cannot_make_read_timeout_safe(self):
        from urllib3.exceptions import NewConnectionError
        try:
            try:
                raise NewConnectionError(None, "old connection")
            except NewConnectionError:
                raise requests.ReadTimeout("current request sent") from None
        except requests.ReadTimeout as error:
            failure = error
        self.open_star([failure, SOLVED, POLISH, ACCEPT], retry=3)
        job_id = self.create_job()
        result = self.terminal(job_id)
        self.assertEqual("failed", result["status"])
        self.assertEqual(1, len(self.outbound))
        self.assertGreater(result["result"]["budget"]["reserved_tokens"], 0)

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

