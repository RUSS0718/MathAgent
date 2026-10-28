"""#99: explicit safe retries through public calls and authenticated Jobs."""

import json
import os
import unittest
from unittest.mock import patch

import requests

from llm_client import InternChatClient
from showcase.adapters import AdapterError, InternModelAdapter, InternStreamAdapter
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget


class Reply:
    """Finite provider substitute; never opens a socket."""

    def __init__(self, *, status=200, retry_after=None, content="ok"):
        self.status_code = status
        self.headers = {} if retry_after is None else {"Retry-After": retry_after}
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def close(self):
        pass

    def json(self):
        return {"model": "intern-s2", "choices": [{"finish_reason": "stop",
                "message": {"content": self.content}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}

    def iter_content(self, chunk_size=1):
        if self.streaming:
            data = self.json()
            data["choices"][0]["delta"] = data["choices"][0].pop("message")
            yield ("data: " + json.dumps(data) + "\n\ndata: [DONE]\n\n").encode()
        else:
            yield json.dumps(self.json()).encode()


class SafeRetryCallTest(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {"INTERN_API_KEY": "offline-99"}))
        self.sleeps = []
        self.enterContext(patch("llm_client.time.sleep", side_effect=self.sleeps.append))

    def call(self, streaming, replies, *, attempts=6, limits=None, metadata=None,
             retry=1, metered=True, on_wait=None):
        client = InternChatClient(timeout=180, retry=retry, safe_retry_attempts=attempts)
        client.api_base = "http://127.0.0.1:1/offline-substitute"
        adapter = (InternStreamAdapter if streaming else InternModelAdapter)(client, max_tokens=256)
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("safe-99", limits or RunBudgetLimits(max_runtime_seconds=180))
        self.budget = budget

        def respond(*args, **kwargs):
            value = replies.pop(0)
            if isinstance(value, BaseException):
                raise value
            value.streaming = streaming
            return value

        if on_wait:
            self.enterContext(patch("llm_client.time.sleep", side_effect=on_wait))
        self.post = self.enterContext(patch("llm_client.requests.post", side_effect=respond))
        self.error = None
        with bind_budget(budget if metered else None):
            try:
                if streaming:
                    result = list(adapter.stream_complete(
                        [{"role": "user", "content": "Return ok"}], metadata=metadata))[-1]
                    self.attempts = result["attempts"]
                    return result["text"]
                result = adapter.complete([{"role": "user", "content": "Return ok"}], metadata=metadata)
                self.attempts = result.request_attempts
                return result.text
            except AdapterError as error:
                self.error = error
                self.attempts = error.request_attempts
                return None

    def test_explicit_six_attempts_have_bounded_backoff_and_one_logical_identity(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                self.sleeps.clear()
                self.assertIsNone(self.call(streaming, [requests.ConnectTimeout()] * 7))
                self.assertEqual(6, self.post.call_count)
                self.assertEqual([1, 2, 4, 8, 15], self.sleeps)
                self.assertEqual([1, 2, 3, 4, 5, 6], [a["attempt_index"] for a in self.attempts])
                self.assertEqual(6, len({a["attempt_id"] for a in self.attempts}))
                self.assertEqual(1, len({a["logical_call_id"] for a in self.attempts}))
                self.assertTrue(all(a["dispatch_status"] == "not_submitted" for a in self.attempts))
                snapshot = self.budget.snapshot()
                self.assertEqual((1, 6, 0, 0), (snapshot["logical_calls"], snapshot["http_attempts"],
                                 snapshot["reserved_tokens"], snapshot["charged_tokens"]))
