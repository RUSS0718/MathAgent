"""Issue #98: explicit metered requests preserve endpoint and redirect policy."""

import os
import unittest
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import AdapterError, InternModelAdapter, InternStreamAdapter
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget


class RedirectPolicyTest(unittest.TestCase):
    def make_adapter(self, streaming, **client_options):
        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            client = InternChatClient(timeout=3, retry=3, **client_options)
        return (InternStreamAdapter if streaming else InternModelAdapter)(client, max_tokens=32)

    def invoke(self, adapter, streaming, budget):
        with bind_budget(budget):
            if streaming:
                return list(adapter.stream_complete([{"role": "user", "content": "offline"}],
                            metadata={"role": "explore", "strict_completion": True}))
            return adapter.complete([{"role": "user", "content": "offline"}],
                                    metadata={"role": "explore", "strict_completion": True})

    def test_budgeted_adapters_forward_client_endpoint_policy(self):
        for streaming in (False, True):
            for option in ("loopback_only", "provider_endpoint_only"):
                with self.subTest(streaming=streaming, option=option):
                    ledger = RunBudgetLedger()
                    self.addCleanup(ledger.close)
                    budget = ledger.ensure(f"policy-{streaming}-{option}", RunBudgetLimits())
                    adapter = self.make_adapter(streaming, **{option: True})
                    observed = []

                    def events(_url, **kwargs):
                        observed.append(kwargs)
                        raise RuntimeError("offline transport seam")
                        yield

                    with patch("showcase.request_transport.response_events", side_effect=events):
                        with self.assertRaises(AdapterError):
                            self.invoke(adapter, streaming, budget)
                    self.assertEqual(1, len(observed))
                    self.assertTrue(observed[0].get(option, False))
                    other = "provider_endpoint_only" if option == "loopback_only" else "loopback_only"
                    self.assertFalse(observed[0].get(other, False))

    def test_redirect_is_one_failed_metered_attempt_without_automatic_follow(self):
        for streaming in (False, True):
            for status in (307, 308):
                with self.subTest(streaming=streaming, status=status):
                    ledger = RunBudgetLedger()
                    self.addCleanup(ledger.close)
                    budget = ledger.ensure(f"redirect-{streaming}-{status}", RunBudgetLimits())
                    adapter = self.make_adapter(streaming)
                    calls = []

                    class Reply:
                        status_code = status

                        def raise_for_status(self):
                            pass

                        def iter_content(self, chunk_size=1):
                            yield b"redirect"

                        def close(self):
                            pass

                    def post(_url, **kwargs):
                        calls.append(kwargs)
                        return Reply()

                    with patch("showcase.request_transport.requests.post", side_effect=post):
                        with self.assertRaises(AdapterError) as caught:
                            self.invoke(adapter, streaming, budget)
                    self.assertEqual("http_status", caught.exception.category)
                    self.assertEqual(1, len(calls))
                    self.assertIs(calls[0].get("allow_redirects"), False)
                    attempt, = ledger.attempts(budget.run_id)
                    self.assertEqual(status, attempt["http_status"])
                    self.assertEqual(1, budget.snapshot()["http_attempts"])
    def test_unbudgeted_official_client_keeps_default_post_arguments(self):
        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            client = InternChatClient(timeout=3, retry=1)
        response = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return response

        with patch("llm_client.requests.post", return_value=Reply()) as post:
            self.assertEqual("ok", client.chat([{"role": "user", "content": "offline"}]))
        self.assertEqual(1, post.call_count)
        self.assertNotIn("allow_redirects", post.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
