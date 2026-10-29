"""#99: explicit safe retries through public calls and authenticated Jobs."""

import json
import os
import time
import unittest
from email.utils import formatdate
from types import SimpleNamespace
from unittest.mock import patch

import requests

from llm_client import InternChatClient
from showcase.adapters import AdapterError, InternModelAdapter, InternStreamAdapter
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget
from tests.star_product_support import ACCEPT, POLISH, SOLVED, RawProviderContent, StarJobFixture
from tests.test_star_product_planning import FEATURES


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
             retry=1, metered=True, on_wait=None, timeout=180):
        client = InternChatClient(timeout=timeout, retry=retry, safe_retry_attempts=attempts)
        client.api_base = "http://127.0.0.1:1/offline-substitute"
        adapter = (InternStreamAdapter if streaming else InternModelAdapter)(client, max_tokens=256)
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("safe-99", limits or RunBudgetLimits(max_runtime_seconds=180))
        self.budget = budget
        self.original_deadline = budget.snapshot()["deadline_at"]

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

    def test_exhausted_http_or_held_429_tokens_stop_before_waiting(self):
        for streaming in (False, True):
            for name, failure, limits in (
                ("http", requests.ConnectTimeout(), RunBudgetLimits(max_http_attempts=1)),
                ("tokens", Reply(status=429, retry_after="2"), RunBudgetLimits(max_tokens=650)),
            ):
                with self.subTest(streaming=streaming, resource=name):
                    self.sleeps.clear()
                    self.assertIsNone(self.call(streaming, [failure, Reply()], limits=limits))
                    self.assertEqual(1, self.post.call_count)
                    self.assertEqual([], self.sleeps)
                    snapshot = self.budget.snapshot()
                    self.assertEqual(1, snapshot["http_attempts"])
                    if name == "tokens":
                        self.assertEqual(1, snapshot["unknown_attempts"])
                        self.assertGreater(snapshot["reserved_tokens"], 256)
                        self.assertEqual(snapshot["reserved_tokens"], snapshot["charged_tokens"])

    def test_insufficient_request_phase_batch_or_run_time_never_waits(self):
        for streaming in (False, True):
            for options in (
                {"timeout": .1}, {"metadata": {"phase_deadline_at": time.time() + .1}},
                {"metadata": {"batch_deadline_at": time.time() + .1}},
                {"limits": RunBudgetLimits(max_runtime_seconds=.1)},
            ):
                with self.subTest(streaming=streaming, options=options):
                    self.sleeps.clear()
                    self.call(streaming, [requests.ConnectTimeout(), Reply()], **options)
                    self.assertEqual(1, self.post.call_count)
                    self.assertEqual([], self.sleeps)
                    self.assertEqual(self.original_deadline, self.budget.snapshot()["deadline_at"])

    def test_capacity_consumed_during_wait_is_rechecked_before_dispatch(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                def consume_capacity(delay):
                    other = self.budget.model_call("concurrent")
                    other.before_attempt({"attempt_id": "concurrent-attempt", "max_tokens": 1}, 1)

                self.assertIsNone(self.call(streaming, [requests.ConnectTimeout(), Reply()],
                                  limits=RunBudgetLimits(max_http_attempts=2), on_wait=consume_capacity))
                self.assertEqual(1, self.post.call_count)
                self.assertEqual(2, self.budget.snapshot()["http_attempts"])

    def test_old_three_cap_and_unmetered_retry_behavior_are_preserved(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                self.sleeps.clear()
                self.call(streaming, [requests.ConnectTimeout()] * 7, attempts=None, retry=8)
                self.assertEqual(3, self.post.call_count)
                self.assertEqual([1, 2], self.sleeps)
        self.sleeps.clear()
        self.call(False, [requests.ReadTimeout()] * 3, metered=False, retry=2)
        self.assertEqual(2, self.post.call_count)
        self.assertEqual([1], self.sleeps)
        self.assertEqual(0, self.budget.snapshot()["http_attempts"])

    def test_f02_unknown_and_terminal_failures_are_never_resent(self):
        for streaming in (False, True):
            for name, failure in (
                ("400", Reply(status=400)), ("401", Reply(status=401)),
                ("500", Reply(status=500)), ("503", Reply(status=503)),
                ("read_timeout", requests.ReadTimeout()),
                ("read_timeout_with_429", requests.ReadTimeout(response=Reply(status=429, retry_after="0"))),
                ("sent_connection", requests.ConnectionError()),
                ("incomplete_body", requests.exceptions.ChunkedEncodingError()),
            ):
                with self.subTest(streaming=streaming, failure=name):
                    self.sleeps.clear()
                    self.assertIsNone(self.call(streaming, [failure, Reply()]))
                    self.assertEqual(1, self.post.call_count)
                    self.assertEqual([], self.sleeps)
                    snapshot = self.budget.snapshot()
                    self.assertEqual(1, snapshot["http_attempts"])
                    self.assertEqual(1, snapshot["unknown_attempts"])
                    self.assertGreater(snapshot["reserved_tokens"], 256)
                    self.assertEqual(self.original_deadline, snapshot["deadline_at"])

    def test_adapter_lazy_client_supports_explicit_retry_configuration(self):
        self.sleeps.clear()
        adapter = InternModelAdapter(client_retry=1, client_safe_retry_attempts=6, max_tokens=256)
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("lazy", RunBudgetLimits())
        response = Reply()
        response.streaming = False
        with patch("llm_client.requests.post", side_effect=[requests.ConnectTimeout()] * 5 + [response]) as post:
            with bind_budget(budget):
                result = adapter.complete([{"role": "user", "content": "ok"}])
        self.assertEqual("ok", result.text)
        self.assertEqual(6, post.call_count)
        self.assertEqual([1, 2, 4, 8, 15], self.sleeps)

    def test_stream_client_without_retry_option_keeps_single_attempt_default(self):
        client = SimpleNamespace(api_base="http://127.0.0.1:1/offline", authorization="offline")
        adapter = InternStreamAdapter(client, max_tokens=256)
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("default-stream", RunBudgetLimits())
        response = Reply()
        response.streaming = True
        with patch("llm_client.requests.post", return_value=response) as post:
            with bind_budget(budget):
                result = list(adapter.stream_complete([{"role": "user", "content": "ok"}]))[-1]
        self.assertEqual("ok", result["text"])
        self.assertEqual(1, post.call_count)
        self.assertEqual(1, result["attempts"][0]["retry_limit"])

    def test_f02_valid_429_uses_retry_after_and_keeps_each_unknown_charge(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                self.sleeps.clear()
                self.assertEqual("ok", self.call(streaming,
                    [Reply(status=429, retry_after="2")] * 5 + [Reply()]))
                self.assertEqual([2, 2, 2, 2, 2], self.sleeps)
                self.assertEqual(6, self.post.call_count)
                snapshot = self.budget.snapshot()
                self.assertEqual((1, 6, 5), (snapshot["logical_calls"], snapshot["http_attempts"],
                                           snapshot["unknown_attempts"]))
                self.assertEqual(10, snapshot["provider_known"]["total_tokens"])
                self.assertGreater(snapshot["reserved_tokens"], 5 * 256)
                self.assertEqual(snapshot["reserved_tokens"] + 10, snapshot["charged_tokens"])

    def test_f02_retry_after_http_date_and_invalid_values(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming, retry_after="date"):
                self.sleeps.clear()
                self.assertEqual("ok", self.call(streaming,
                    [Reply(status=429, retry_after=formatdate(time.time() + 10, usegmt=True)), Reply()]))
                self.assertEqual(1, len(self.sleeps))
                self.assertTrue(8 < self.sleeps[0] <= 10)
            for value in (None, "", "invalid", "-1", "nan", "inf", "999999"):
                with self.subTest(streaming=streaming, retry_after=value):
                    self.sleeps.clear()
                    self.assertIsNone(self.call(streaming, [Reply(status=429, retry_after=value), Reply()]))
                    self.assertEqual(1, self.post.call_count)
                    self.assertEqual([], self.sleeps)

    def test_explicit_attempt_configuration_is_bounded_and_counts_initial_request(self):
        for value in (0, 7, -1, True, "6", 6.0):
            with self.subTest(invalid=value):
                with self.assertRaisesRegex(ValueError, "safe_retry_attempts_invalid"):
                    InternChatClient(safe_retry_attempts=value)
        for streaming in (False, True):
            for value in range(1, 7):
                with self.subTest(streaming=streaming, attempts=value):
                    self.sleeps.clear()
                    self.call(streaming, [requests.ConnectTimeout()] * 7, attempts=value)
                    self.assertEqual(value, self.post.call_count)
                    self.assertEqual([1, 2, 4, 8, 15][:value - 1], self.sleeps)


class SafeRetryJobTest(StarJobFixture, unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {"INTERN_API_KEY": "offline-99"}))
        real_sleep = time.sleep
        self.waits = []

        def wait(seconds):
            if seconds >= 1:
                self.waits.append(seconds)
            else:
                real_sleep(seconds)

        self.enterContext(patch("llm_client.time.sleep", side_effect=wait))

    def open_explicit(self, streaming, replies):
        client = InternChatClient(timeout=180, retry=1, safe_retry_attempts=6)
        adapter = (InternStreamAdapter if streaming else InternModelAdapter)(client, max_tokens=256)
        self.open_star(replies, SHOWCASE_STAR_ADAPTER=adapter, SHOWCASE_STAR_FEATURES=FEATURES,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=4, max_http_attempts=14))

    def test_transport_retry_and_protocol_repair_use_independent_logical_identities(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                self.waits.clear()
                self.open_explicit(streaming, [requests.ConnectTimeout()] * 5 + [RawProviderContent("not json")]
                                   + [requests.ConnectTimeout()] * 5 + [SOLVED, POLISH, ACCEPT])
                job_id = self.create_job()
                job = self.terminal(job_id)
                self.assertEqual("succeeded", job["status"], job)
                self.assertEqual("1+1=2", job["result"]["final_response"])
                snapshot = job["result"]["budget"]
                self.assertEqual((4, 14, 0), (snapshot["logical_calls"], snapshot["http_attempts"],
                                            snapshot["reserved_tokens"]))
                self.assertEqual(40, snapshot["provider_known"]["total_tokens"])
                self.assertEqual([1, 2, 4, 8, 15] * 2, self.waits)
                attempts = [a for a in job["result"]["request_attempts"] if a["role"] == "explore"]
                self.assertEqual(12, len(attempts))
                self.assertEqual(12, len({a["attempt_id"] for a in attempts}))
                self.assertEqual(2, len({a["logical_call_id"] for a in attempts}))
                self.assertEqual([1, 2, 3, 4, 5, 6] * 2, [a["attempt_index"] for a in attempts])
                contexts = [r for r in self.outbound if r["role"] == "explore"]
                self.assertEqual(1, len({r["call_id"] for r in contexts[:6]}))
                self.assertEqual({contexts[0]["call_id"] + ":repair-1"},
                                 {r["call_id"] for r in contexts[6:]})

    def test_read_timeout_retains_one_unknown_attempt_and_review_gate(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                self.waits.clear()
                self.open_explicit(streaming, [requests.ReadTimeout(), SOLVED, POLISH, ACCEPT])
                job_id = self.create_job()
                job = self.terminal(job_id)
                self.assertEqual("failed", job["status"], job)
                self.assertEqual(1, self.post.call_count)
                self.assertEqual([], self.waits)
                self.assertEqual("needs_review", job["result"]["solver"]["recovery"]["status"])
                snapshot = job["result"]["budget"]
                self.assertEqual((1, 1, 1), (snapshot["logical_calls"], snapshot["http_attempts"],
                                            snapshot["unknown_attempts"]))
                self.assertGreater(snapshot["reserved_tokens"], 256)
                evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
                self.assertEqual(snapshot["deadline_at"], evidence["budget"]["deadline_at"])
                self.assertEqual(snapshot["reserved_tokens"], evidence["budget"]["reserved_tokens"])
                original = job["result"]["request_attempts"][0]
                recorded = self.report(job_id)["request_attempts"]
                self.assertEqual([original["attempt_id"]], [a["attempt_id"] for a in recorded])
