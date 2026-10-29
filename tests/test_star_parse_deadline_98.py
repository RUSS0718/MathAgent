"""Issue #98: local response processing may not outlive the call deadline."""

import json
import os
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import AdapterError, InternModelAdapter, InternStreamAdapter
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget


class ProcessingDeadlineTest(unittest.TestCase):
    def test_complete_json_parsing_after_phase_deadline_stops_consumer_but_settles_usage(self):
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("slow-json-parse", RunBudgetLimits(max_runtime_seconds=8))
        entered, release, finished = (threading.Event() for _ in range(3))
        self.addCleanup(release.set)
        body = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
                           "usage": {"prompt_tokens": 7, "completion_tokens": 3,
                                     "total_tokens": 10}}).encode()
        actions, errors, sends = [], [], []

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

        def events(*_args, **_kwargs):
            sends.append(True)
            yield "headers", Reply()
            yield "bytes", body
            yield "complete", None

        def loads(value, *args, **kwargs):
            if isinstance(value, (bytes, bytearray)) and bytes(value) == body:
                entered.set()
                if not release.wait(4):
                    raise AssertionError("JSON parser not released")
            return json.loads(value, *args, **kwargs)

        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            adapter = InternModelAdapter(InternChatClient(timeout=3, retry=1), max_tokens=32)

        def run():
            try:
                with bind_budget(budget):
                    phase_deadline = time.time() + .35
                    response = adapter.complete([{"role": "user", "content": "offline"}],
                        metadata={"role": "explore", "phase_deadline_at": phase_deadline,
                                  "strict_completion": True})
                    actions.append(response.text)
            except BaseException as exc:
                errors.append(exc)
            finally:
                finished.set()

        fake_json = SimpleNamespace(loads=loads, dumps=json.dumps)
        with (patch("llm_client.json", fake_json),
              patch("showcase.request_transport.response_events", side_effect=events)):
            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            self.assertTrue(entered.wait(3))
            # The caller must finish while the parser is still blocked. A local
            # timeout is not evidence that the remote attempt was cancelled.
            self.assertTrue(finished.wait(2), "caller waited for the blocked parser")
            pending, = ledger.attempts(budget.run_id)
            self.assertEqual("timeout", pending["error_category"])
            self.assertEqual(1, budget.snapshot()["unresolved_attempts"])
            self.assertGreater(budget.snapshot()["reserved_tokens"], 0)
            self.assertFalse(release.is_set())
            release.set()
            worker.join(1)
            limit = time.monotonic() + 3
            while budget.snapshot()["unresolved_attempts"] and time.monotonic() < limit:
                time.sleep(.01)
        self.assertEqual([True], sends)
        self.assertEqual([], actions)
        self.assertEqual(1, len(errors))
        self.assertIsInstance(errors[0], AdapterError)
        self.assertEqual("timeout", errors[0].category)
        attempt, = ledger.attempts(budget.run_id)
        self.assertEqual("success", attempt["status"])
        self.assertEqual(10, attempt["usage"]["total_tokens"])
        self.assertEqual(0, budget.snapshot()["unresolved_attempts"])
        self.assertEqual(0, budget.snapshot()["reserved_tokens"])


    def test_late_invalid_json_keeps_missing_usage_reserved(self):
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("late-invalid-json", RunBudgetLimits(max_runtime_seconds=8))
        entered, release, finished = (threading.Event() for _ in range(3))
        self.addCleanup(release.set)
        body = b"{invalid"
        errors = []

        class Reply:
            status_code = 200
            def raise_for_status(self):
                pass

        def events(*_args, **_kwargs):
            yield "headers", Reply()
            yield "bytes", body
            yield "complete", None

        def loads(value, *args, **kwargs):
            if isinstance(value, (bytes, bytearray)) and bytes(value) == body:
                entered.set()
                if not release.wait(5):
                    raise AssertionError("invalid parser not released")
            return json.loads(value, *args, **kwargs)

        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            adapter = InternModelAdapter(InternChatClient(timeout=3, retry=1), max_tokens=32)

        def run():
            try:
                with bind_budget(budget):
                    deadline = time.time() + .5
                    adapter.complete([{"role": "user", "content": "offline"}],
                        metadata={"role": "explore", "phase_deadline_at": deadline})
            except BaseException as exc:
                errors.append(exc)
            finally:
                finished.set()

        with (patch("llm_client.json", SimpleNamespace(loads=loads, dumps=json.dumps)),
              patch("showcase.request_transport.response_events", side_effect=events)):
            threading.Thread(target=run, daemon=True).start()
            self.assertTrue(entered.wait(3))
            self.assertTrue(finished.wait(2))
            pending, = ledger.attempts(budget.run_id)
            self.assertEqual("timeout", pending["error_category"])
            self.assertGreater(budget.snapshot()["reserved_tokens"], 0)
            release.set()
            until = time.monotonic() + 3
            while (ledger.attempts(budget.run_id)[0].get("error_category") != "invalid_response"
                   and time.monotonic() < until):
                time.sleep(.01)
            settled, = ledger.attempts(budget.run_id)
        self.assertEqual("timeout", errors[0].category)
        self.assertEqual(pending["attempt_id"], settled["attempt_id"])
        self.assertEqual("invalid_response", settled["error_category"])
        self.assertIsNone(settled["usage"]["total_tokens"])
        self.assertGreater(budget.snapshot()["reserved_tokens"], 0)
    def test_slow_stream_parse_detaches_and_reconciles_buffered_complete_reply(self):
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("slow-stream-reconcile", RunBudgetLimits(max_runtime_seconds=8))
        entered, release, finished = (threading.Event() for _ in range(3))
        self.addCleanup(release.set)
        packet = {"choices": [{"delta": {"content": "fragment"}, "finish_reason": "stop"}],
                  "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}
        body = ("data: " + json.dumps(packet) + "\n\ndata: [DONE]\n\n").encode()
        errors, chunks = [], []

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

            def iter_content(self, chunk_size=1):
                yield body

            def close(self):
                pass

        def loads(value, *args, **kwargs):
            if isinstance(value, str) and '"fragment"' in value:
                entered.set()
                if not release.wait(4):
                    raise AssertionError("SSE parser not released")
            return json.loads(value, *args, **kwargs)

        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            adapter = InternStreamAdapter(InternChatClient(timeout=3, retry=1), max_tokens=32)

        def run():
            try:
                with bind_budget(budget):
                    deadline = time.time() + .5
                    chunks.extend(adapter.stream_complete(
                        [{"role": "user", "content": "offline"}],
                        metadata={"role": "explore", "phase_deadline_at": deadline,
                                  "strict_completion": True}))
            except BaseException as exc:
                errors.append(exc)
            finally:
                finished.set()

        with (patch("showcase.adapters.json", SimpleNamespace(loads=loads, dumps=json.dumps)),
              patch("showcase.request_transport.requests.post", return_value=Reply())):
            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            self.assertTrue(entered.wait(3))
            self.assertTrue(finished.wait(2), "caller waited for the blocked SSE parser")
            pending, = ledger.attempts(budget.run_id)
            self.assertEqual("timeout", pending["error_category"])
            self.assertEqual(1, budget.snapshot()["unresolved_attempts"])
            self.assertGreater(budget.snapshot()["reserved_tokens"], 0)
            self.assertFalse(release.is_set())
            release.set()
            worker.join(1)
            until = time.monotonic() + 3
            while budget.snapshot()["unresolved_attempts"] and time.monotonic() < until:
                time.sleep(.01)
        self.assertEqual([], chunks)
        self.assertEqual("timeout", errors[0].category)
        attempt, = ledger.attempts(budget.run_id)
        self.assertEqual("success", attempt["status"])
        self.assertEqual(10, attempt["usage"]["total_tokens"])
        self.assertEqual(0, budget.snapshot()["unresolved_attempts"])
        self.assertEqual(0, budget.snapshot()["reserved_tokens"])
    def test_late_partial_parse_cannot_replace_complete_invalid_stream_evidence(self):
        self.assert_late_partial_preserves_invalid_evidence()

    def test_delayed_partial_worker_cannot_block_complete_invalid_stream_evidence(self):
        start = threading.Thread.start
        original_loads = json.loads
        full_fragment_parsed = threading.Event()
        parse_order = []

        def observed_loads(value, *args, **kwargs):
            parsed = original_loads(value, *args, **kwargs)
            if (threading.current_thread().name == "showcase-late-settlement"
                    and isinstance(value, str) and '"fragment"' in value):
                parse_order.append("complete")
                full_fragment_parsed.set()
            return parsed

        def delayed_start(worker):
            if worker.name == "showcase-response-processing":
                target = worker._target

                def delayed():
                    if full_fragment_parsed.wait(3):
                        parse_order.append("partial")
                        target()

                worker._target = delayed
            return start(worker)

        with (patch.object(threading.Thread, "start", delayed_start),
              patch.object(json, "loads", observed_loads)):
            self.assert_late_partial_preserves_invalid_evidence()
        self.assertEqual(["complete", "partial"], parse_order)

    def assert_late_partial_preserves_invalid_evidence(self):
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("partial-after-invalid", RunBudgetLimits(max_runtime_seconds=8))
        entered, release, finished, partial_done = (threading.Event() for _ in range(4))
        self.addCleanup(release.set)
        packet = {"choices": [{"delta": {"content": "fragment"}, "finish_reason": "stop"}],
                  "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}
        body = ("data: " + json.dumps(packet) + "\n\ndata: {bad\n\ndata: [DONE]\n\n").encode()
        errors = []
        original_settle = RunBudgetLedger.settle

        class Reply:
            status_code = 200
            def raise_for_status(self):
                pass
            def iter_content(self, chunk_size=1):
                yield body
            def close(self):
                pass

        def loads(value, *args, **kwargs):
            # Block only the partial parser, even if full-body late parsing wins scheduling.
            if (threading.current_thread().name == "showcase-response-processing"
                    and isinstance(value, str) and '"fragment"' in value and not entered.is_set()):
                entered.set()
                if not release.wait(5):
                    raise AssertionError("first parse not released")
            return json.loads(value, *args, **kwargs)

        def settle(ledger, run_id, attempt_id, event):
            outcome = original_settle(ledger, run_id, attempt_id, event)
            if release.is_set() and event.get("total_tokens") == 10:
                partial_done.set()
            return outcome

        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            adapter = InternStreamAdapter(InternChatClient(timeout=3, retry=1), max_tokens=32)

        def run():
            try:
                with bind_budget(budget):
                    deadline = time.time() + .5
                    list(adapter.stream_complete([{"role": "user", "content": "offline"}],
                         metadata={"role": "explore", "phase_deadline_at": deadline,
                                   "strict_completion": True}))
            except BaseException as exc:
                errors.append(exc)
            finally:
                finished.set()

        with (patch("showcase.adapters.json", SimpleNamespace(loads=loads, dumps=json.dumps)),
              patch("showcase.request_transport.requests.post", return_value=Reply()),
              patch.object(RunBudgetLedger, "settle", settle)):
            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            self.assertTrue(entered.wait(3))
            self.assertTrue(finished.wait(2))
            until = time.monotonic() + 3
            while (ledger.attempts(budget.run_id)[0].get("error_category") != "invalid_response"
                   and time.monotonic() < until):
                time.sleep(.01)
            before, = ledger.attempts(budget.run_id)
            self.assertEqual("invalid_response", before["error_category"])
            self.assertEqual("error", before["status"])
            self.assertEqual(10, before["usage"]["total_tokens"])
            release.set()
            self.assertTrue(partial_done.wait(3))
            after, = ledger.attempts(budget.run_id)
        self.assertEqual("timeout", errors[0].category)
        self.assertEqual("error", after["status"])
        self.assertEqual("invalid_response", after["error_category"])
        self.assertEqual(10, after["usage"]["total_tokens"])
    def test_complete_stream_assembly_after_deadline_settles_once_without_result(self):
        from showcase.request_attempts import record_attempts

        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("slow-stream-assembly", RunBudgetLimits(max_runtime_seconds=8))
        entered, release, finished = (threading.Event() for _ in range(3))
        self.addCleanup(release.set)
        packet = {"choices": [{"delta": {}, "finish_reason": "stop"}],
                  "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}
        body = ("data: " + json.dumps(packet) + "\n\ndata: [DONE]\n\n").encode()
        chunks, errors = [], []
        calls = []

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

        def events(*_args, **_kwargs):
            yield "headers", Reply()
            yield "bytes", body
            yield "complete", None

        def slow_record(*args, **kwargs):
            calls.append(True)
            if len(calls) == 1:
                entered.set()
                if not release.wait(4):
                    raise AssertionError("stream assembly not released")
            return record_attempts(*args, **kwargs)

        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            adapter = InternStreamAdapter(InternChatClient(timeout=3, retry=1), max_tokens=32)

        def run():
            deadline = time.time() + .35
            try:
                with bind_budget(budget):
                    chunks.extend(adapter.stream_complete(
                        [{"role": "user", "content": "offline"}],
                        metadata={"role": "explore", "phase_deadline_at": deadline,
                                  "strict_completion": True}))
            except BaseException as exc:
                errors.append(exc)
            finally:
                finished.set()

        with (patch("showcase.adapters.record_attempts", side_effect=slow_record),
              patch("showcase.request_transport.response_events", side_effect=events)):
            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            self.assertTrue(entered.wait(3))
            self.assertTrue(finished.wait(2), "caller waited for stream assembly")
            self.assertFalse(release.is_set())
            release.set()
            worker.join(1)
        self.assertEqual([], chunks)
        self.assertEqual(1, len(errors))
        self.assertEqual("timeout", errors[0].category)
        self.assertEqual(1, len(errors[0].request_attempts))
        attempt, = ledger.attempts(budget.run_id)
        self.assertEqual("success", attempt["status"])
        self.assertEqual(10, attempt["usage"]["total_tokens"])
        self.assertEqual(0, budget.snapshot()["unresolved_attempts"])
        self.assertEqual(0, budget.snapshot()["reserved_tokens"])
    def test_stream_processing_or_consumer_past_deadline_cannot_emit_more(self):
        for pause in ("parse", "consumer"):
            with self.subTest(pause=pause):
                self.check_stream_deadline(pause)

    def check_stream_deadline(self, pause):
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("slow-stream-" + pause, RunBudgetLimits(max_runtime_seconds=8))
        deadline_at = []
        entered, release, finished = (threading.Event() for _ in range(3))
        self.addCleanup(release.set)
        data = {"choices": [{"delta": {"content": "fragment"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}
        body = ("data: " + json.dumps(data) + "\n\ndata: [DONE]\n\n").encode()
        chunks, errors = [], []

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

        def events(*_args, **_kwargs):
            yield "headers", Reply()
            yield "bytes", body
            yield "complete", None

        def loads(value, *args, **kwargs):
            if pause == "parse" and isinstance(value, str) and '"fragment"' in value:
                entered.set()
                if not release.wait(4):
                    raise AssertionError("SSE parser not released")
            return json.loads(value, *args, **kwargs)

        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            adapter = InternStreamAdapter(InternChatClient(timeout=3, retry=1), max_tokens=32)

        def run():
            try:
                with bind_budget(budget):
                    deadline_at.append(time.time() + .35)
                    for chunk in adapter.stream_complete(
                        [{"role": "user", "content": "offline"}],
                        metadata={"role": "explore", "phase_deadline_at": deadline_at[0],
                                  "strict_completion": True},
                    ):
                        chunks.append(chunk)
                        if pause == "consumer" and chunk["type"] == "text_delta":
                            entered.set()
                            if not release.wait(4):
                                raise AssertionError("stream consumer not released")
            except BaseException as exc:
                errors.append(exc)
            finally:
                finished.set()

        with (patch("showcase.adapters.json", SimpleNamespace(loads=loads, dumps=json.dumps)),
              patch("showcase.request_transport.response_events", side_effect=events)):
            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            self.assertTrue(entered.wait(3))
            time.sleep(max(0, deadline_at[0] - time.time()) + .05)
            release.set()
            self.assertTrue(finished.wait(3))
            worker.join(1)
            until = time.monotonic() + 3
            while (ledger.attempts(budget.run_id)[0]["usage"]["total_tokens"] is None
                   and time.monotonic() < until):
                time.sleep(.01)
        self.assertEqual(["text_delta"] if pause == "consumer" else [],
                         [chunk["type"] for chunk in chunks])
        self.assertEqual(1, len(errors))
        self.assertIsInstance(errors[0], AdapterError)
        self.assertEqual("timeout", errors[0].category)
        attempt, = ledger.attempts(budget.run_id)
        self.assertEqual(10, attempt["usage"]["total_tokens"])
        self.assertEqual(1, budget.snapshot()["unresolved_attempts"])
        self.assertGreater(budget.snapshot()["reserved_tokens"], 0)

if __name__ == "__main__":
    unittest.main()
