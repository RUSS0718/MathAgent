"""Compatibility tests for responses that finish after the caller deadline."""

import json
import os
import threading
import time
import unittest
from unittest.mock import patch

import requests

from llm_client import InternChatClient
from showcase.adapters import AdapterError, InternStreamAdapter
from showcase.request_transport import response_events
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget


class FakeResponse:
    """Provide a deterministic response body without making a network request."""

    def __init__(self, body=b"late body", stream_error=None):
        self.body = body
        self.stream_error = stream_error
        self.closed = threading.Event()

    def iter_content(self, chunk_size):
        """Yield one body chunk, then optionally fail while reading the body."""
        yield self.body
        if self.stream_error is not None:
            raise self.stream_error

    def close(self):
        """Match the response cleanup interface used by the transport."""
        self.closed.set()


class RequestTransportLateCallbackTest(unittest.TestCase):
    """Keep late-response callback arity compatible across transport versions."""

    def run_late_callback(self, response, callback, callback_called):
        """Release a mocked response only after the transport detaches at deadline."""
        request_released = threading.Event()

        def fake_post(*_args, **_kwargs):
            if not request_released.wait(timeout=2):
                raise TimeoutError("test did not release the mocked response")
            return response

        with patch("showcase.request_transport.requests.post", side_effect=fake_post):
            events = response_events(
                "http://local.invalid",
                deadline=time.monotonic() - 1,
                timeout=5,
                on_late_response=callback,
            )
            with self.assertRaises(requests.ReadTimeout):
                next(events)
            request_released.set()
            self.assertTrue(response.closed.wait(timeout=2))

    def test_four_argument_callback_receives_late_complete_response(self):
        """Legacy callbacks still receive completed response metadata after timeout."""
        calls = []
        callback_called = threading.Event()

        def legacy_callback(response, body, headers_seconds, total_seconds):
            calls.append((response, body, headers_seconds, total_seconds))
            callback_called.set()

        self.run_late_callback(FakeResponse(), legacy_callback, callback_called)

        self.assertEqual(1, len(calls))
        self.assertIsInstance(calls[0][0], FakeResponse)
        self.assertEqual(b"late body", calls[0][1])

    def test_five_argument_callback_receives_complete_flag(self):
        """Current callbacks retain the fifth body-completion argument."""
        calls = []
        callback_called = threading.Event()

        def current_callback(response, body, headers_seconds, total_seconds, body_complete):
            calls.append((response, body, body_complete))
            callback_called.set()

        self.run_late_callback(FakeResponse(), current_callback, callback_called)

        self.assertEqual(1, len(calls))
        self.assertEqual((b"late body", True), calls[0][1:])

    def test_four_argument_callback_is_not_called_for_partial_response(self):
        """A four-argument callback cannot mark an incomplete response successful."""
        calls = []
        callback_called = threading.Event()

        def legacy_callback(response, body, headers_seconds, total_seconds):
            calls.append((response, body, headers_seconds, total_seconds))
            callback_called.set()

        self.run_late_callback(
            FakeResponse(
                b'{"usage":{"input_tokens":3}}',
                requests.exceptions.ChunkedEncodingError("incomplete body"),
            ),
            legacy_callback,
            callback_called,
        )

        self.assertEqual([], calls)
        self.assertFalse(callback_called.is_set())

    def test_five_argument_callback_reports_incomplete_late_body(self):
        """Current callbacks receive false when late body reading fails."""
        calls = []
        callback_called = threading.Event()

        def current_callback(response, body, headers_seconds, total_seconds, body_complete):
            calls.append((response, body, body_complete))
            callback_called.set()

        self.run_late_callback(
            FakeResponse(
                b'{"usage":{"input_tokens":3}}',
                requests.exceptions.ChunkedEncodingError("incomplete body"),
            ),
            current_callback,
            callback_called,
        )

        self.assertEqual(1, len(calls))
        self.assertEqual((b'{"usage":{"input_tokens":3}}', False), calls[0][1:])

    def test_chunk_arriving_after_late_cutoff_is_included_before_settlement(self):
        """The cutoff callback includes the chunk whose arrival crosses the limit."""
        body = b'data: {"type":"message_delta","usage":{"output_tokens":3}}\n\n'

        class SlowResponse(FakeResponse):
            def iter_content(self, chunk_size):
                time.sleep(0.1)
                yield body

        response = SlowResponse()
        calls = []

        def callback(_response, raw_body, _headers, _total, body_complete):
            calls.append((raw_body, body_complete))

        with patch("showcase.request_transport.requests.post", return_value=response):
            events = response_events(
                "http://local.invalid",
                deadline=time.monotonic() + 0.02,
                timeout=0.04,
                on_late_response=callback,
            )
            with self.assertRaises(requests.ReadTimeout):
                list(events)

        self.assertTrue(response.closed.wait(timeout=2))
        self.assertEqual([(body, False)], calls)

    def test_late_callback_failure_does_not_invoke_callback_twice(self):
        """A callback error is contained and never retried by the reader thread."""
        response = FakeResponse()
        calls = []
        callback_called = threading.Event()

        def callback(*_args):
            calls.append(True)
            callback_called.set()
            raise RuntimeError("callback failed")

        self.run_late_callback(response, callback, callback_called)
        self.assertEqual([True], calls)

    def test_late_window_expiry_settles_observed_stream_usage(self):
        """Usage read before the late-window cutoff still updates its attempt."""
        events = [
            {"choices": [{"delta": {"content": "answer"}}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}], "model": "intern-s2"},
            {"choices": [], "usage": {"completion_tokens": 3}},
            "[DONE]",
        ]
        body = b"".join(
            ("data: " + event + "\n\n").encode()
            if isinstance(event, str)
            else ("data: " + json.dumps(event) + "\n\n").encode()
            for event in events
        )

        class SlowResponse(FakeResponse):
            status_code = 200

            def raise_for_status(self):
                """Match a successful HTTP response."""

            def iter_content(self, chunk_size):
                """Deliver a usage-only Chat delta after detach, then hold the reader."""
                time.sleep(0.08)
                yield body
                for _ in range(80):
                    time.sleep(0.005)
                    yield b":\n"

        response = SlowResponse()
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("late-window-expiry", RunBudgetLimits(max_runtime_seconds=0.05))
        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-test-key"}):
            client = InternChatClient(timeout=0.2, retry=1, thinking_mode=True)
        client.api_base = "http://local.invalid"
        adapter = InternStreamAdapter(client, max_tokens=64)

        with (
            patch("showcase.request_transport.requests.post", return_value=response),
            bind_budget(budget),
            self.assertRaises(AdapterError) as raised,
        ):
            list(adapter.stream_complete(
                [{"role": "user", "content": "Return an answer"}],
                metadata={"role": "solver", "timeout_seconds": 0.2},
            ))

        self.assertEqual("timeout", raised.exception.category)
        self.assertTrue(response.closed.wait(timeout=2))
        snapshot = budget.snapshot()
        attempt, = ledger.attempts("late-window-expiry")
        self.assertEqual(3, snapshot["provider_known"]["completion_tokens"])
        self.assertIsNone(snapshot["provider_known"]["prompt_tokens"])
        self.assertIsNone(snapshot["provider_known"]["total_tokens"])
        self.assertEqual("unknown", attempt["status"])
        self.assertEqual("transport_observed", attempt["dispatch_status"])
        self.assertEqual(1, snapshot["unresolved_attempts"])
        self.assertGreater(snapshot["reserved_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
