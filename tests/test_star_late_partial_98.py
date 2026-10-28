"""Issue #98: repeated late updates do not replace original attempt facts."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from llm_client import InternChatClient
from showcase.adapters import AdapterError, InternModelAdapter
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget


class LatePartialUsageTest(unittest.TestCase):
    def test_late_finished_reply_without_usage_closes_outcome_not_reservation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "budget.sqlite"
            ledger = RunBudgetLedger(database_path=path)
            budget = ledger.ensure("late-no-usage", RunBudgetLimits(max_runtime_seconds=10))
            callbacks = []

            def transport(_url, *, on_late_response, **_kwargs):
                callbacks.append(on_late_response)
                raise requests.ReadTimeout("offline deadline")

            with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
                adapter = InternModelAdapter(InternChatClient(timeout=2, retry=1))
            with patch("showcase.request_transport.response_events", side_effect=transport):
                with bind_budget(budget), self.assertRaises(AdapterError):
                    adapter.complete([{"role": "user", "content": "offline"}],
                                     metadata={"strict_completion": True})
            ledger.close()
            response = requests.Response()
            response.status_code = 200
            body = json.dumps({"choices": [{"finish_reason": "stop", "message": {
                "content": "late"}}]}).encode()
            callbacks[0](response, body, .1, .2, True)
            reopened = RunBudgetLedger(database_path=path)
            try:
                attempt = reopened.attempts("late-no-usage")[0]
                self.assertEqual("success", attempt["status"])
                self.assertEqual("unknown", attempt["metering_status"])
                snapshot = reopened.snapshot("late-no-usage")
                self.assertEqual(0, snapshot["unresolved_attempts"])
                self.assertGreater(snapshot["reserved_tokens"], 0)
                self.assertIsNone(snapshot["provider_known"]["total_tokens"])
            finally:
                reopened.close()

    def test_partial_late_usage_can_finish_after_original_ledger_is_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "budget.sqlite"
            ledger = RunBudgetLedger(database_path=path)
            budget = ledger.ensure("late-closed", RunBudgetLimits(max_runtime_seconds=10))
            callbacks = []

            def transport(_url, *, on_late_response, **_kwargs):
                callbacks.append(on_late_response)
                raise requests.ReadTimeout("offline deadline")

            with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
                adapter = InternModelAdapter(InternChatClient(timeout=2, retry=1))
            with patch("showcase.request_transport.response_events", side_effect=transport):
                with bind_budget(budget), self.assertRaises(AdapterError):
                    adapter.complete([{"role": "user", "content": "offline"}],
                                     metadata={"strict_completion": True})
            ledger.close()
            response = requests.Response()
            response.status_code = 200

            def body(usage):
                return json.dumps({"choices": [{"finish_reason": "stop", "message": {
                    "content": "late"}}], "usage": usage}).encode()

            callbacks[0](response, body({"prompt_tokens": 7}), .1, .2, True)
            callbacks[0](response, body({"prompt_tokens": 7, "completion_tokens": 3,
                                          "total_tokens": 10}), .1, .3, True)
            reopened = RunBudgetLedger(database_path=path)
            try:
                attempt = reopened.attempts("late-closed")[0]
                self.assertEqual(10, attempt["usage"]["total_tokens"])
                self.assertEqual(0, reopened.snapshot("late-closed")["reserved_tokens"])
                self.assertEqual(1, reopened.snapshot("late-closed")["http_attempts"])
            finally:
                reopened.close()

    def test_repeated_late_usage_only_fills_missing_fields(self):
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("late-partial", RunBudgetLimits(max_runtime_seconds=10))
        callbacks = []

        def transport(_url, *, on_late_response, **_kwargs):
            callbacks.append(on_late_response)
            raise requests.ReadTimeout("offline deadline")

        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            adapter = InternModelAdapter(InternChatClient(timeout=2, retry=1))
        with patch("showcase.request_transport.response_events", side_effect=transport):
            with bind_budget(budget), self.assertRaises(AdapterError):
                adapter.complete([{"role": "user", "content": "offline"}],
                                 metadata={"strict_completion": True})
        attempt = ledger.attempts("late-partial")[0]
        original_id, deadline = attempt["attempt_id"], attempt["deadline_at"]
        response = requests.Response()
        response.status_code = 200

        def body(usage):
            return json.dumps({"choices": [{"finish_reason": "stop", "message": {
                "content": "late"}}], "usage": usage}).encode()

        callbacks[0](response, body({"prompt_tokens": 7}), .1, .2, True)
        callbacks[0](response, body({"prompt_tokens": 99, "completion_tokens": 3,
                                      "total_tokens": 10}), .1, .3, True)
        conflict = ledger.attempts("late-partial")[0]
        self.assertEqual(7, conflict["usage"]["prompt_tokens"])
        self.assertIsNone(conflict["usage"]["completion_tokens"])
        self.assertGreater(budget.snapshot()["reserved_tokens"], 0)
        callbacks[0](response, body({"prompt_tokens": 7, "completion_tokens": 3,
                                      "total_tokens": 10}), .1, .3, True)
        settled = ledger.attempts("late-partial")[0]
        self.assertEqual(original_id, settled["attempt_id"])
        self.assertEqual(deadline, settled["deadline_at"])
        self.assertEqual({"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
                         {k: settled["usage"][k] for k in
                          ("prompt_tokens", "completion_tokens", "total_tokens")})
        self.assertEqual(0, budget.snapshot()["reserved_tokens"])
        charged_before = budget.snapshot()["charged_tokens"]
        callbacks[0](response, body({"prompt_tokens": 999, "completion_tokens": 999,
                                      "total_tokens": 1998}), .1, .4, True)
        self.assertEqual(settled, ledger.attempts("late-partial")[0])
        self.assertEqual(1, budget.snapshot()["http_attempts"])
        self.assertEqual(charged_before, budget.snapshot()["charged_tokens"])


if __name__ == "__main__":
    unittest.main()
