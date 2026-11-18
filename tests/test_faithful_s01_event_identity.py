"""Distinct payloads sharing an SSE ID remain visible at the adapter boundary."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import requests

from showcase.adapters import InternStreamAdapter
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget
from tests.test_faithful_s01_timeout import STREAM_POLICY, identified_content_packet


class FaithfulEventIdentityTest(unittest.TestCase):
    def test_reused_sse_id_does_not_discard_new_content(self):
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure(
            "s01-reused-event-id", RunBudgetLimits(), stream_timeout_policy=STREAM_POLICY
        )
        client = SimpleNamespace(
            api_base="http://127.0.0.1:1/chat/completions",
            authorization="Bearer synthetic",
            model="intern-s2-test",
            timeout=180,
            retry=1,
            thinking_mode=False,
            loopback_only=True,
        )
        response = requests.Response()
        response.status_code = 200
        events = [
            ("headers", response),
            ("bytes", identified_content_packet("event-1", "first ")),
            ("bytes", identified_content_packet("event-1", "second")),
            ("bytes", b"data: [DONE]\n\n"),
            ("complete", None),
        ]
        with bind_budget(budget), patch(
            "showcase.request_transport.response_events", return_value=iter(events)
        ):
            chunks = list(InternStreamAdapter(client, max_tokens=64).stream_complete(
                [{"role": "user", "content": "synthetic"}], metadata={"role": "explore"}
            ))

        self.assertEqual(["first ", "second"], [
            chunk["text"] for chunk in chunks if chunk.get("type") == "text_delta"
        ])
        self.assertEqual("first second", chunks[-1]["text"])


if __name__ == "__main__":
    unittest.main()
