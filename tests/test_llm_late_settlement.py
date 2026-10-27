"""Regression tests for metered Intern responses settled after a timeout."""

import json
import os
import threading
import unittest
from unittest.mock import patch

import requests

from llm_client import ChatClientError, InternChatClient
from showcase.adapters import AdapterError, InternModelAdapter
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget


def _completion_body():
    """Return one complete, usage-bearing OpenAI-compatible completion."""
    return json.dumps(
        {
            "id": "response-late",
            "model": "intern-s2",
            "choices": [
                {"message": {"content": "answer"}, "finish_reason": "stop"}
            ],
            "usage": {
                "prompt_tokens": 7,
                "completion_tokens": 3,
                "total_tokens": 10,
            },
        }
    ).encode()


class InternLateSettlementTest(unittest.TestCase):
    """Keep late provider usage and attempt state coherent after timeout."""

    def setUp(self):
        """Create a local budgeted client; response transport is mocked per test."""
        self.ledger = RunBudgetLedger()
        self.addCleanup(self.ledger.close)
        run_budget = self.ledger.ensure(
            "late-settlement", RunBudgetLimits(max_runtime_seconds=60)
        )
        self.call_budget = run_budget.model_call(role="solver")
        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-test-key"}):
            self.client = InternChatClient(timeout=2, retry=1)
        self.client.api_base = "http://127.0.0.1/never-requested"

    def _run_until_timeout(self, response_events):
        """Run the public response envelope against a mocked late transport."""
        with patch(
            "showcase.request_transport.response_events", side_effect=response_events
        ):
            with self.assertRaises(ChatClientError) as raised:
                self.client.chat_response(
                    [{"role": "user", "content": "offline test"}],
                    max_tokens=16,
                    _attempt_budget=self.call_budget,
                )
        return raised.exception

    def test_late_http_error_keeps_usage_without_becoming_success(self):
        """A complete 500 response can update usage but remains an HTTP error."""
        callbacks = []
        response = requests.Response()
        response.status_code = 500

        def fake_response_events(_url, *, on_late_response, **_kwargs):
            callbacks.append(on_late_response)
            raise requests.ReadTimeout("simulated_deadline")

        error = self._run_until_timeout(fake_response_events)
        callbacks[0](response, _completion_body(), 0.01, 0.02, True)

        attempt = self.ledger.attempts("late-settlement")[0]
        self.assertEqual("error", attempt["status"])
        self.assertEqual("http_status", attempt["error_category"])
        self.assertEqual(500, attempt["http_status"])
        self.assertEqual("error", error.attempts[0]["status"])
        self.assertEqual("http_status", error.attempts[0]["error_category"])
        self.assertEqual(500, error.attempts[0]["http_status"])
        self.assertEqual(7, attempt["usage"]["prompt_tokens"])
        self.assertEqual(3, attempt["usage"]["completion_tokens"])
        self.assertEqual(10, attempt["usage"]["total_tokens"])
        self.assertEqual(7, error.attempts[0]["prompt_tokens"])
        self.assertEqual(3, error.attempts[0]["completion_tokens"])
        self.assertEqual(10, error.attempts[0]["total_tokens"])

    def test_timeout_finalizer_does_not_overwrite_late_success(self):
        """A completed late settlement stays successful when timeout unwinds."""
        rendezvous = threading.Barrier(2)
        callback_done = threading.Event()
        response = requests.Response()
        response.status_code = 200

        def fake_response_events(_url, *, on_late_response, **_kwargs):
            def settle_from_reader():
                rendezvous.wait(timeout=2)
                on_late_response(response, _completion_body(), 0.01, 0.02, True)
                callback_done.set()

            reader = threading.Thread(target=settle_from_reader, daemon=True)
            reader.start()
            rendezvous.wait(timeout=2)
            if not callback_done.wait(timeout=2):
                raise AssertionError("late settlement did not finish")
            reader.join(timeout=2)
            raise requests.ReadTimeout("simulated_deadline")

        error = self._run_until_timeout(fake_response_events)

        attempt = self.ledger.attempts("late-settlement")[0]
        self.assertEqual("success", attempt["status"])
        self.assertEqual(3, attempt["usage"]["completion_tokens"])
        self.assertEqual("success", error.attempts[0]["status"])
        self.assertEqual(3, error.attempts[0]["completion_tokens"])
        self.assertEqual(1, len(self.ledger.attempts("late-settlement")))

    def test_exception_attempt_snapshot_tracks_late_success(self):
        """The raised envelope retains the same attempt state for reconciliation."""
        callbacks = []
        response = requests.Response()
        response.status_code = 200

        def fake_response_events(_url, *, on_late_response, **_kwargs):
            callbacks.append(on_late_response)
            raise requests.ReadTimeout("simulated_deadline")

        error = self._run_until_timeout(fake_response_events)
        self.assertEqual("error", error.attempts[0]["status"])
        callbacks[0](response, _completion_body(), 0.01, 0.02, True)

        self.assertEqual("success", error.attempts[0]["status"])
        self.assertEqual(7, error.attempts[0]["prompt_tokens"])
        self.assertEqual(3, error.attempts[0]["completion_tokens"])
        self.assertEqual(10, error.attempts[0]["total_tokens"])
        ledger_attempt = self.ledger.attempts("late-settlement")[0]
        self.assertEqual(error.attempts[0]["attempt_id"], ledger_attempt["attempt_id"])
        self.assertEqual(error.attempts[0]["status"], ledger_attempt["status"])
        self.assertEqual(
            error.attempts[0]["prompt_tokens"], ledger_attempt["usage"]["prompt_tokens"]
        )
        self.assertEqual(
            error.attempts[0]["completion_tokens"],
            ledger_attempt["usage"]["completion_tokens"],
        )
        self.assertEqual(
            error.attempts[0]["total_tokens"], ledger_attempt["usage"]["total_tokens"]
        )

    def test_adapter_attempt_projection_tracks_usage_settled_after_timeout(self):
        """A late reconciliation reaches the adapter's public attempt record."""
        callbacks = []
        response = requests.Response()
        response.status_code = 200

        def fake_response_events(_url, *, on_late_response, **_kwargs):
            callbacks.append(on_late_response)
            raise requests.ReadTimeout("simulated_deadline")

        adapter = InternModelAdapter(self.client, max_tokens=16)
        with patch("showcase.request_transport.response_events", side_effect=fake_response_events):
            with bind_budget(self.call_budget):
                with self.assertRaises(AdapterError) as raised:
                    adapter.complete(
                        [{"role": "user", "content": "offline test"}],
                        metadata={"role": "solver"},
                    )

        attempt = raised.exception.request_attempts[0]
        self.assertEqual("error", attempt["status"])
        callbacks[0](response, _completion_body(), 0.01, 0.02, True)

        self.assertEqual("success", attempt["status"])
        self.assertEqual(7, attempt["usage"]["prompt_tokens"])
        self.assertEqual(3, attempt["usage"]["completion_tokens"])
        self.assertEqual(10, attempt["usage"]["total_tokens"])

    def test_late_malformed_completion_keeps_usage_without_success(self):
        """Malformed 2xx completion shapes retain usage but cannot be successful."""
        malformed_responses = (
            {"choices": "not-a-list"},
            {"choices": [None]},
            {"choices": [{"message": "not-a-mapping"}]},
            {"choices": [{"message": {"content": 7}}]},
        )
        response = requests.Response()
        response.status_code = 200

        for index, partial in enumerate(malformed_responses):
            with self.subTest(response=partial):
                callbacks = []
                payload = {
                    "id": f"malformed-{index}",
                    "model": "intern-s2",
                    **partial,
                    "usage": {
                        "prompt_tokens": 7,
                        "completion_tokens": 3,
                        "total_tokens": 10,
                    },
                }

                def fake_response_events(_url, *, on_late_response, **_kwargs):
                    callbacks.append(on_late_response)
                    raise requests.ReadTimeout("simulated_deadline")

                error = self._run_until_timeout(fake_response_events)
                callbacks[0](response, json.dumps(payload).encode(), 0.01, 0.02, True)

                attempt = self.ledger.attempts("late-settlement")[-1]
                self.assertEqual("error", attempt["status"])
                self.assertEqual("invalid_response", attempt["error_category"])
                self.assertEqual(7, attempt["usage"]["prompt_tokens"])
                self.assertEqual(3, attempt["usage"]["completion_tokens"])
                self.assertEqual(10, attempt["usage"]["total_tokens"])
                self.assertEqual("error", error.attempts[0]["status"])
                self.assertEqual(7, error.attempts[0]["prompt_tokens"])
                self.assertEqual(3, error.attempts[0]["completion_tokens"])
                self.assertEqual(10, error.attempts[0]["total_tokens"])


if __name__ == "__main__":
    unittest.main()
