"""Keep local token admission failures distinct from remote stream outcomes."""

from __future__ import annotations

import os
import unittest
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternStreamAdapter
from showcase.run_budget import BudgetExhausted, RunBudgetLedger, RunBudgetLimits, bind_budget


class StreamBudgetAdmissionTest(unittest.TestCase):
    def test_token_admission_rejection_preserves_logical_only_reservation(self):
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        limits = RunBudgetLimits(
            max_model_calls=31,
            max_http_attempts=31,
            max_tokens=2_097_152,
            max_runtime_seconds=60,
        )
        budget = ledger.ensure("stream-budget-admission-127", limits)

        # Recreate the archived boundary with 30 completed HTTP attempts whose
        # known usage charges 2,074,314 tokens, leaving 22,838 below the cap.
        for index in range(30):
            call_budget = budget.model_call(role="meta")
            attempt = {
                "attempt_id": uuid.uuid4().hex,
                "attempt_index": 1,
                "max_tokens": 32_768,
                "started_at_utc": datetime.now(UTC).isoformat(),
                "status": "pending",
            }
            prompt_tokens = 36_376 if index < 29 else 36_370
            call_budget.before_attempt(attempt, input_estimate=prompt_tokens)
            call_budget.after_attempt({
                **attempt,
                "status": "success",
                "http_status": 200,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": 32_768,
                "total_tokens": prompt_tokens + 32_768,
            })

        before = budget.snapshot()
        self.assertEqual(30, before["logical_calls"])
        self.assertEqual(30, before["http_attempts"])
        self.assertEqual(2_074_314, before["charged_tokens"])
        self.assertEqual(22_838, limits.max_tokens - before["charged_tokens"])

        with patch.dict(os.environ, {
            "INTERN_API_KEY": "offline-placeholder",
            "INTERN_API_BASE": "http://127.0.0.1:5000/api/v1/chat/completions",
        }):
            adapter = InternStreamAdapter(
                InternChatClient(timeout=5, retry=1), max_tokens=32_768
            )

        with (
            patch("showcase.request_transport.strict_loopback_post") as post,
            patch.object(ledger, "settle", wraps=ledger.settle) as settle,
            bind_budget(budget),
        ):
            with self.assertRaises(BudgetExhausted) as caught:
                list(adapter.stream_complete(
                    [{"role": "user", "content": "offline test input"}],
                    metadata={"role": "meta"},
                ))

        self.assertEqual("run_model_budget_exhausted", str(caught.exception))
        post.assert_not_called()
        settle.assert_not_called()

        after = budget.snapshot()
        self.assertEqual(31, after["logical_calls"])
        self.assertEqual(30, after["http_attempts"])
        self.assertEqual(before["charged_tokens"], after["charged_tokens"])
        self.assertEqual(30, len(ledger.attempts(budget.run_id)))


if __name__ == "__main__":
    unittest.main()
