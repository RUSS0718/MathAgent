"""Issue #123: public adapter SSE transport and metering contracts, offline only."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import requests

from showcase.adapters import AdapterError, InternStreamAdapter
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget


def packet(value):
    """Encode a synthetic Chat event independently of adapter parsing."""
    return ("data: " + json.dumps(value) + "\n\n").encode()


class InternSSEReportRuleTest(unittest.TestCase):
    """Keep the machine-readable handoff conservative about thinking defaults."""

    def test_automatic_streaming_requires_live_profile_and_explicit_thinking(self):
        report = Path(__file__).parents[1] / "docs/research/intern-sse-123.md"
        content = report.read_text(encoding="utf-8")
        rule_json = content.split("```json\n", 1)[1].split("\n```", 1)[0]
        rule = json.loads(rule_json)

        self.assertFalse(rule["current_defaults"]["automatic_streaming_enabled"])
        self.assertFalse(rule["current_defaults"]["omission_means_thinking_disabled"])
        self.assertEqual([], rule["evidence"]["provider_live"]["verified_profiles"])
        thinking = next(
            condition for condition in rule["automatic_streaming"]["eligible_all"]
            if condition["path"] == "request.payload.thinking_mode"
        )
        self.assertEqual("equals_profile_value", thinking["op"])
        self.assertEqual("provider_live_verified", rule["automatic_streaming"]["enable_only_with_matching_profile_status"])


class InternSSEContractTest(unittest.TestCase):
    """Observe envelopes and public attempts through stream_complete only."""

    def stream(self, body, failure=None, thinking_mode=True):
        """Inject the external HTTP boundary; never construct a provider client."""
        client = SimpleNamespace(api_base="http://127.0.0.1:1/api/v1/chat/completions",
                                 authorization="Bearer synthetic", model="intern-s2",
                                 timeout=2, retry=1, thinking_mode=thinking_mode, loopback_only=True)
        response = requests.Response()
        response.status_code = 200

        def events(_url, **kwargs):
            payload = json.loads(kwargs["data"])
            self.assertIs(True, payload["stream"])
            if thinking_mode is None:
                self.assertNotIn("thinking_mode", payload)
            else:
                self.assertIs(thinking_mode, payload["thinking_mode"])
            self.assertNotIn("tools", payload)
            self.assertNotIn("stream_options", payload)
            yield "headers", response
            yield "bytes", body
            if failure is not None:
                raise failure
            yield "complete", None

        with patch("showcase.request_transport.response_events", side_effect=events):
            return list(InternStreamAdapter(client, max_tokens=32).stream_complete(
                [{"role": "user", "content": "synthetic"}],
                metadata={},
            ))

    def test_complete_without_usage_is_transport_success_with_unknown_metering(self):
        body = packet({"choices": [{"delta": {"content": "2"}, "finish_reason": "stop"}]})
        result = self.stream(body + b"data: [DONE]\n\n")[-1]
        self.assertEqual("2", result["text"])
        attempt = result["attempts"][0]
        self.assertEqual("success", attempt["status"])
        self.assertEqual("unknown", attempt["metering_status"])
        self.assertEqual("missing", attempt["usage_source"])
        self.assertIsNone(attempt["usage"]["total_tokens"])

    def test_unset_thinking_setting_is_omitted_not_serialized_as_false(self):
        body = packet({"choices": [{"delta": {"content": "2"}, "finish_reason": "stop"}]})
        result = self.stream(body + b"data: [DONE]\n\n", thinking_mode=None)[-1]
        self.assertEqual("2", result["text"])

    def test_usage_only_tail_after_finish_is_preserved(self):
        body = packet({"choices": [{"delta": {"content": "2"}, "finish_reason": "stop"}]})
        body += packet({"choices": [], "usage": {
            "prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}})
        result = self.stream(body + b"data: [DONE]\n\n")[-1]
        self.assertEqual("2", result["text"])
        self.assertEqual("known", result["attempts"][0]["metering_status"])
        self.assertEqual(10, result["attempts"][0]["usage"]["total_tokens"])

    def test_empty_finish_reason_with_done_is_not_strict_completion(self):
        client = SimpleNamespace(api_base="http://127.0.0.1:1/api/v1/chat/completions",
                                 authorization="Bearer synthetic", model="intern-s2",
                                 timeout=2, retry=1, thinking_mode=True, loopback_only=True)
        response = requests.Response()
        response.status_code = 200
        body = packet({"choices": [{"delta": {"content": "partial"}, "finish_reason": ""}]})
        body += b"data: [DONE]\n\n"

        def events(_url, **_kwargs):
            yield "headers", response
            yield "bytes", body
            yield "complete", None

        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("strict-empty-finish", RunBudgetLimits(max_runtime_seconds=5))
        adapter = InternStreamAdapter(client, max_tokens=32)
        with patch("showcase.request_transport.response_events", side_effect=events):
            with bind_budget(budget), self.assertRaises(AdapterError) as caught:
                list(adapter.stream_complete(
                    [{"role": "user", "content": "synthetic"}],
                    metadata={"role": "explore", "strict_completion": True},
                ))
        self.assertEqual("missing_finish_reason", caught.exception.category)
        self.assertEqual(1, budget.snapshot()["unresolved_attempts"])

    def test_empty_content_can_complete_transport_without_proving_task_success(self):
        result = self.stream(packet({"choices": [{"delta": {}, "finish_reason": "stop"}]})
                             + b"data: [DONE]\n\n")[-1]
        self.assertEqual("", result["text"])
        self.assertEqual("success", result["attempts"][0]["status"])
        # Role/schema and task success belong to InternModelPort, not this envelope.

    def test_malformed_event_is_sanitized_and_has_no_result(self):
        with self.assertRaises(AdapterError) as caught:
            self.stream(b"data: {broken\n\n")
        self.assertEqual("invalid_response", caught.exception.category)

    def test_disconnect_and_timeout_never_return_a_complete_envelope(self):
        partial = packet({"choices": [{"delta": {"content": "partial"}}]})
        for failure, category in ((requests.ConnectionError("synthetic"), "connectivity"),
                                  (requests.ReadTimeout("synthetic"), "timeout")):
            with self.subTest(category=category), self.assertRaises(AdapterError) as caught:
                self.stream(partial, failure)
            self.assertEqual(category, caught.exception.category)
            self.assertIsNone(caught.exception.request_attempts[0]["usage"]["total_tokens"])
