"""Offline acceptance tests at the explicit Showcase model-call boundary."""

import json
import os
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import AdapterError, InternModelAdapter, InternStreamAdapter
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget
from showcase.run_control import RunStopped
from tests.star_product_support import SOLVED, StarJobFixture


class DeadlineContractTest(unittest.TestCase):
    def test_late_reconciliation_is_idempotent_for_original_attempt(self):
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("late-idempotent", RunBudgetLimits(max_runtime_seconds=30))
        call = budget.model_call("explore")
        event = {"attempt_id": "original-attempt", "max_tokens": 100, "status": "pending"}
        call.before_attempt(event, input_estimate=20)
        call.after_attempt({**event, "status": "error", "error_category": "timeout"})
        self.assertGreater(budget.snapshot()["reserved_tokens"], 0)
        call.after_attempt({**event, "status": "success", "prompt_tokens": 7,
                            "completion_tokens": 3, "total_tokens": 10})
        settled = budget.snapshot()
        call.after_attempt({**event, "status": "success", "prompt_tokens": 70,
                            "completion_tokens": 30, "total_tokens": 100})
        repeated = budget.snapshot()
        self.assertEqual(1, repeated["http_attempts"])
        self.assertEqual(settled["provider_known"], repeated["provider_known"])
        self.assertEqual(10, repeated["provider_known"]["total_tokens"])
        self.assertEqual(0, repeated["reserved_tokens"])
    def test_phase_deadline_is_earlier_than_request_and_run_deadlines(self):
        release = threading.Event()
        self.addCleanup(release.set)
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                release.wait(4)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        env = {"INTERN_API_KEY": "offline-placeholder",
               "INTERN_API_BASE": f"http://127.0.0.1:{server.server_port}"}
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("deadline-phase", RunBudgetLimits(max_runtime_seconds=5))
        with patch.dict(os.environ, env):
            adapter = InternModelAdapter(InternChatClient(timeout=2, retry=1, loopback_only=True))
            started = time.monotonic()
            phase_deadline = time.time() + 0.15
            with bind_budget(budget), self.assertRaises(AdapterError) as caught:
                adapter.complete([{"role": "user", "content": "offline"}], metadata={
                    "role": "explore", "timeout_seconds": 1,
                    "phase_deadline_at": phase_deadline,
                })
        self.assertEqual("timeout", caught.exception.category)
        self.assertLess(time.monotonic() - started, 1.5)
        release.set()
        self.assertGreater(budget.snapshot()["reserved_tokens"], 0)
        self.assertAlmostEqual(phase_deadline, ledger.attempts("deadline-phase")[0]["deadline_at"], delta=0.05)
    def test_missing_finish_marker_is_unknown_when_contract_explicitly_enabled(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                body = json.dumps({"choices": [{"message": {"content": "not final"}}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        env = {"INTERN_API_KEY": "offline-placeholder",
               "INTERN_API_BASE": f"http://127.0.0.1:{server.server_port}"}
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("missing-finish", RunBudgetLimits(max_runtime_seconds=5))
        with patch.dict(os.environ, env):
            adapter = InternModelAdapter(InternChatClient(timeout=2, retry=3, loopback_only=True))
            with bind_budget(budget), self.assertRaises(AdapterError) as caught:
                adapter.complete([{"role": "user", "content": "offline"}],
                    metadata={"role": "explore", "strict_completion": True})
        self.assertEqual("missing_finish_reason", caught.exception.category)
        self.assertEqual(1, budget.snapshot()["http_attempts"])
        self.assertEqual(1, budget.snapshot()["unresolved_attempts"])
        self.assertGreater(budget.snapshot()["reserved_tokens"], 0)
        attempt = ledger.attempts("missing-finish")[0]
        self.assertEqual("missing_finish_reason", attempt["error_category"])
        self.assertEqual(10, attempt["usage"]["total_tokens"])
    def test_stream_done_without_finish_reason_is_unknown(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                body = (b'data: {"choices":[{"delta":{"content":"partial"}}],'
                        b'"usage":{"prompt_tokens":7,"completion_tokens":3,"total_tokens":10}}\n\n'
                        b'data: [DONE]\n\n')
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        env = {"INTERN_API_KEY": "offline-placeholder",
               "INTERN_API_BASE": f"http://127.0.0.1:{server.server_port}"}
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("stream-missing-finish", RunBudgetLimits(max_runtime_seconds=5))
        with patch.dict(os.environ, env):
            adapter = InternStreamAdapter(InternChatClient(timeout=2, retry=3, loopback_only=True))
            with bind_budget(budget), self.assertRaises(AdapterError) as caught:
                list(adapter.stream_complete([{"role": "user", "content": "offline"}],
                    metadata={"role": "explore", "strict_completion": True}))
        self.assertEqual("missing_finish_reason", caught.exception.category)
        self.assertEqual(1, budget.snapshot()["unresolved_attempts"])
        self.assertEqual(10, ledger.attempts("stream-missing-finish")[0]["usage"]["total_tokens"])
    def test_stream_eof_without_done_has_distinct_unknown_category(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                body = (b'data: {"choices":[{"delta":{"content":"partial"},"finish_reason":"stop"}],'
                        b'"usage":{"prompt_tokens":7,"completion_tokens":3,"total_tokens":10}}\n\n')
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        env = {"INTERN_API_KEY": "offline-placeholder",
               "INTERN_API_BASE": f"http://127.0.0.1:{server.server_port}"}
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("stream-missing-done", RunBudgetLimits(max_runtime_seconds=5))
        with patch.dict(os.environ, env):
            adapter = InternStreamAdapter(InternChatClient(timeout=2, retry=3, loopback_only=True))
            with bind_budget(budget), self.assertRaises(AdapterError) as caught:
                list(adapter.stream_complete([{"role": "user", "content": "offline"}],
                    metadata={"role": "explore", "strict_completion": True}))
        self.assertEqual("missing_stream_terminal", caught.exception.category)
        self.assertEqual(1, budget.snapshot()["unresolved_attempts"])
        self.assertGreater(budget.snapshot()["reserved_tokens"], 0)
        self.assertEqual(10, ledger.attempts("stream-missing-done")[0]["usage"]["total_tokens"])
    def test_late_reply_without_finish_marker_remains_unknown(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                time.sleep(0.35)
                body = json.dumps({"choices": [{"message": {"content": "late"}}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        env = {"INTERN_API_KEY": "offline-placeholder",
               "INTERN_API_BASE": f"http://127.0.0.1:{server.server_port}"}
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("late-missing-finish", RunBudgetLimits(max_runtime_seconds=5))
        with patch.dict(os.environ, env):
            adapter = InternModelAdapter(InternChatClient(timeout=2, retry=3, loopback_only=True))
            with bind_budget(budget), self.assertRaises(AdapterError):
                adapter.complete([{"role": "user", "content": "offline"}], metadata={
                    "role": "explore", "timeout_seconds": 0.15, "strict_completion": True})
            limit = time.monotonic() + 2
            while time.monotonic() < limit and budget.snapshot()["provider_known"]["total_tokens"] is None:
                time.sleep(0.01)
        snapshot = budget.snapshot()
        self.assertEqual(10, snapshot["provider_known"]["total_tokens"])
        self.assertEqual(1, snapshot["unresolved_attempts"])
        self.assertGreater(snapshot["reserved_tokens"], 0)
        self.assertEqual("missing_finish_reason", ledger.attempts("late-missing-finish")[0]["error_category"])
    def test_late_stream_without_done_remains_unknown(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                time.sleep(0.35)
                body = (b'data: {"choices":[{"delta":{"content":"late"},"finish_reason":"stop"}],'
                        b'"usage":{"prompt_tokens":7,"completion_tokens":3,"total_tokens":10}}\n\n')
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        env = {"INTERN_API_KEY": "offline-placeholder",
               "INTERN_API_BASE": f"http://127.0.0.1:{server.server_port}"}
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("late-stream-no-done", RunBudgetLimits(max_runtime_seconds=5))
        with patch.dict(os.environ, env):
            adapter = InternStreamAdapter(InternChatClient(timeout=2, retry=3, loopback_only=True))
            with bind_budget(budget), self.assertRaises(AdapterError):
                list(adapter.stream_complete([{"role": "user", "content": "offline"}], metadata={
                    "role": "explore", "timeout_seconds": 0.15, "strict_completion": True}))
            limit = time.monotonic() + 2
            while time.monotonic() < limit and budget.snapshot()["provider_known"]["total_tokens"] is None:
                time.sleep(0.01)
        snapshot = budget.snapshot()
        self.assertEqual(10, snapshot["provider_known"]["total_tokens"])
        self.assertEqual(1, snapshot["unresolved_attempts"])
        self.assertGreater(snapshot["reserved_tokens"], 0)
        self.assertEqual("missing_stream_terminal", ledger.attempts("late-stream-no-done")[0]["error_category"])
    def test_batch_and_run_deadlines_win_when_each_is_earliest(self):
        release = threading.Event()
        self.addCleanup(release.set)
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                release.wait(4)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        env = {"INTERN_API_KEY": "offline-placeholder",
               "INTERN_API_BASE": f"http://127.0.0.1:{server.server_port}"}
        with patch.dict(os.environ, env):
            adapter = InternModelAdapter(InternChatClient(timeout=2, retry=3, loopback_only=True))
            for scope in ("batch", "run"):
                with self.subTest(scope=scope):
                    ledger = RunBudgetLedger()
                    try:
                        now = time.time()
                        budget = ledger.ensure(scope, RunBudgetLimits(
                            max_runtime_seconds=0.18 if scope == "run" else 5))
                        expected = budget.snapshot()["deadline_at"] if scope == "run" else now + 0.18
                        metadata = {"role": "explore", "timeout_seconds": 1,
                                    "phase_deadline_at": now + 2,
                                    "batch_deadline_at": expected if scope == "batch" else now + 2}
                        started = time.monotonic()
                        with bind_budget(budget), self.assertRaises((AdapterError, RunStopped)):
                            adapter.complete([{"role": "user", "content": "offline"}], metadata=metadata)
                        self.assertLess(time.monotonic() - started, 1.5)
                        self.assertEqual(1, budget.snapshot()["http_attempts"])
                        self.assertEqual(1, budget.snapshot()["unresolved_attempts"])
                        self.assertGreater(budget.snapshot()["reserved_tokens"], 0)
                        self.assertAlmostEqual(expected, ledger.attempts(scope)[0]["deadline_at"], delta=0.06)
                    finally:
                        ledger.close()

    def test_heartbeat_and_silence_do_not_extend_stream_deadline(self):
        release = threading.Event()
        heartbeat_seen = threading.Event()
        self.addCleanup(release.set)
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                if self.path == "/silent":
                    release.wait(4)
                    return
                while not release.is_set():
                    try:
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
                        heartbeat_seen.set()
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        return
                    release.wait(0.02)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"
        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            for mode in ("silent", "heartbeat"):
                with self.subTest(mode=mode):
                    ledger = RunBudgetLedger()
                    try:
                        budget = ledger.ensure(mode, RunBudgetLimits(max_runtime_seconds=5))
                        client = InternChatClient(timeout=2, retry=3, loopback_only=True)
                        client.api_base = f"{base}/{mode}"
                        adapter = InternStreamAdapter(client)
                        started = time.monotonic()
                        with bind_budget(budget), self.assertRaises(AdapterError) as caught:
                            list(adapter.stream_complete([{"role": "user", "content": "offline"}],
                                metadata={"role": "explore", "timeout_seconds": 0.18}))
                        self.assertEqual("timeout", caught.exception.category)
                        self.assertLess(time.monotonic() - started, 1.5)
                        if mode == "heartbeat":
                            self.assertTrue(heartbeat_seen.is_set())
                        self.assertFalse(release.is_set())
                        self.assertEqual(1, budget.snapshot()["http_attempts"])
                        self.assertGreater(budget.snapshot()["reserved_tokens"], 0)
                    finally:
                        ledger.close()

    def test_missing_usage_is_not_recorded_as_zero(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                body = b'{"choices":[{"finish_reason":"stop","message":{"content":"ok"}}]}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        env = {"INTERN_API_KEY": "offline-placeholder",
               "INTERN_API_BASE": f"http://127.0.0.1:{server.server_port}"}
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("missing-usage", RunBudgetLimits(max_runtime_seconds=5))
        with patch.dict(os.environ, env):
            adapter = InternModelAdapter(InternChatClient(timeout=2, retry=1, loopback_only=True))
            with bind_budget(budget):
                response = adapter.complete([{"role": "user", "content": "offline"}],
                    metadata={"role": "explore", "strict_completion": True})
        self.assertEqual("ok", response.text)
        self.assertEqual("stop", response.finish_reason)
        self.assertIsNone(response.usage["total_tokens"])
        self.assertEqual("unknown", ledger.attempts("missing-usage")[0]["metering_status"])
        self.assertEqual(0, budget.snapshot()["unresolved_attempts"])
        self.assertGreater(budget.snapshot()["reserved_tokens"], 0)
    def test_no_headers_obeys_short_request_deadline_and_holds_unknown_attempt(self):
        release = threading.Event()
        self.addCleanup(release.set)
        requests_seen = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                requests_seen.append(True)
                release.wait(4)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        env = {
            "INTERN_API_KEY": "offline-placeholder",
            "INTERN_API_BASE": f"http://127.0.0.1:{server.server_port}",
        }
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("deadline-no-headers", RunBudgetLimits(max_runtime_seconds=5))
        original_deadline = budget.snapshot()["deadline_at"]
        with patch.dict(os.environ, env):
            adapter = InternModelAdapter(InternChatClient(timeout=2, retry=3, loopback_only=True))
            started = time.monotonic()
            with bind_budget(budget), self.assertRaises(AdapterError) as caught:
                adapter.complete(
                    [{"role": "user", "content": "offline"}],
                    metadata={"role": "explore", "timeout_seconds": 0.15},
                )
        elapsed = time.monotonic() - started
        self.assertEqual("timeout", caught.exception.category)
        self.assertGreaterEqual(elapsed, 0.1)
        self.assertLess(elapsed, 1.5)
        release.set()
        self.assertEqual(1, len(requests_seen))
        self.assertEqual(1, len(ledger.attempts("deadline-no-headers")))
        self.assertGreater(budget.snapshot()["reserved_tokens"], 0)
        self.assertEqual(original_deadline, budget.snapshot()["deadline_at"])


class JobDeadlineContractTest(StarJobFixture, unittest.TestCase):
    def test_missing_terminal_marker_stops_job_in_needs_review_without_retry(self):
        self.open_star([], retry=3, SHOWCASE_STAR_FEATURES={"strict_completion": True})
        received = []

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

            def close(self):
                pass

            def iter_content(self, chunk_size=1):
                body = {"choices": [{"message": {"content": json.dumps(SOLVED)}}],
                        "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}
                yield json.dumps(body).encode()

        def respond(*_args, **_kwargs):
            received.append(True)
            return Reply()

        self.post.side_effect = respond
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("failed", job["status"])
        self.assertEqual("needs_review", job["result"]["solver"]["recovery"]["status"])
        self.assertEqual(1, len(received))
        self.assertEqual(1, job["result"]["budget"]["unresolved_attempts"])
        self.assertEqual("missing_finish_reason", job["result"]["request_attempts"][0]["error_category"])

if __name__ == "__main__":
    unittest.main()
