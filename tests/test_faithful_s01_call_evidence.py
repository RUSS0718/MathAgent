"""Public call-policy evidence is sanitized at the attempt boundary."""

from __future__ import annotations

import hashlib
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import requests

from showcase.adapters import InternStreamAdapter
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget


class FaithfulCallPolicyEvidenceTest(unittest.TestCase):
    def test_opted_in_stream_publishes_sanitized_policy_evidence(self):
        endpoint = "https://user:password@example.invalid/v1/chat?api_key=hidden"
        client = SimpleNamespace(
            api_base=endpoint,
            authorization="Bearer synthetic",
            model="intern-s2-test",
            provider="internal-provider-credential",
            timeout=180,
            retry=1,
            thinking_mode=False,
            loopback_only=False,
        )
        response = requests.Response()
        response.status_code = 200
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure(
            "s01-call-evidence",
            RunBudgetLimits(max_runtime_seconds=60),
            stream_timeout_policy={
                "policy_version": "faithful-stream-v1",
                "soft_prompt_seconds": 1200,
                "effective_idle_seconds": 30,
            },
        )

        def transport(_url, **_kwargs):
            yield "headers", response
            yield "bytes", b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
            yield "bytes", b"data: [DONE]\n\n"
            yield "complete", None

        clock = time.time()
        with (
            patch("showcase.adapters.time.time", return_value=clock),
            patch("showcase.request_transport.response_events", side_effect=transport),
            bind_budget(budget),
        ):
            result = list(InternStreamAdapter(client, max_tokens=8).stream_complete(
                [{"role": "user", "content": "synthetic"}],
                metadata={"role": "explore"},
            ))[-1]

        attempt = result["attempts"][0]
        self.assertEqual("explore", attempt["role"])
        self.assertEqual({
            "policy_version": "faithful-stream-v1",
            "provider": "unknown",
            "endpoint_sha256": hashlib.sha256(endpoint.encode("utf-8")).hexdigest(),
            "provider_timeout_limit": {
                "status": "unknown",
                "seconds": None,
                "source": None,
                "version": None,
                "date": None,
            },
        }, attempt["call_policy_evidence"])
        serialized = json.dumps(attempt)
        for secret in (endpoint, "user", "password", "api_key", "hidden", "internal-provider-credential"):
            self.assertNotIn(secret, serialized)

    def test_public_attempt_drops_unrecognized_nested_evidence_fields(self):
        from llm_response import public_attempt

        attempt = public_attempt({
            "attempt_id": "attempt-1",
            "call_policy_evidence": {
                "policy_version": "faithful-stream-v1",
                "provider": "internal-provider-credential",
                "endpoint_sha256": "a" * 64,
                "provider_timeout_limit": {
                    "status": "claimed",
                    "seconds": 120,
                    "source": "https://secret.invalid/sla",
                    "version": "private-version",
                    "date": "2026-01-02",
                    "api_key": "must-drop",
                },
                "endpoint": "https://user:secret@example.invalid/?token=must-drop",
                "authorization": "Bearer must-drop",
            },
        })

        self.assertEqual({
            "policy_version": "faithful-stream-v1",
            "provider": "unknown",
            "endpoint_sha256": "a" * 64,
            "provider_timeout_limit": {
                "status": "unknown",
                "seconds": None,
                "source": None,
                "version": None,
                "date": None,
            },
        }, attempt["call_policy_evidence"])
        serialized = json.dumps(attempt)
        for secret in ("must-drop", "secret.invalid", "private-version", "internal-provider-credential"):
            self.assertNotIn(secret, serialized)
        self.assertNotIn("endpoint", attempt["call_policy_evidence"])

    def test_legacy_attempt_has_no_new_policy_evidence_field(self):
        from llm_response import public_attempt

        attempt = public_attempt({"attempt_id": "legacy-1", "requests_timeout_seconds": 180})

        self.assertEqual(180, attempt["requests_timeout_seconds"])
        self.assertNotIn("call_policy_evidence", attempt)


if __name__ == "__main__":
    unittest.main()
