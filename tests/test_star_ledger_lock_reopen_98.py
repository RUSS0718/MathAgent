"""Public timeout and successful-call checks with a contended persisted ledger."""

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from llm_client import InternChatClient
from showcase.adapters import AdapterError, InternModelAdapter, InternStreamAdapter
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget


class LockContentionProbe:
    """Pause the named late worker only after a real failed nonblocking acquire."""

    def __init__(self, lock, contended, resume):
        self.lock, self.contended, self.resume = lock, contended, resume

    def acquire(self, *args, **kwargs):
        if threading.current_thread().name == "test-late-contender" and "timeout" in kwargs:
            if self.lock.acquire(blocking=False):
                return True
            self.contended.set()
            if not self.resume.wait(8):
                return False
        return self.lock.acquire(*args, **kwargs)

    def release(self):
        self.lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_args):
        self.release()


class PersistedLedgerRaceTest(unittest.TestCase):
    def test_contended_late_reply_survives_close_and_reopen_without_duplicate_charge(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                self.check_close_and_reopen(streaming)

    def check_close_and_reopen(self, streaming):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "budget.sqlite"
            ledger = RunBudgetLedger(database_path=path)
            observer = RunBudgetLedger(database_path=path)
            held, release, contended, resume, done = (threading.Event() for _ in range(5))
            budget = ledger.ensure(f"reopen-{streaming}", RunBudgetLimits(max_runtime_seconds=10))
            ledger.lock = LockContentionProbe(ledger.lock, contended, resume)
            callbacks, sends, failures, results, late_errors = [], [], [], [], []
            deadline = time.time() + 1.2

            class Reply:
                status_code = 200

                def raise_for_status(self):
                    pass

            reply = Reply()
            usage = {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}
            choice = {"finish_reason": "stop", "delta" if streaming else "message": {"content": "ok"}}
            packet = json.dumps({"choices": [choice], "usage": usage})
            body = ("data: " + packet + "\n\ndata: [DONE]\n\n").encode() if streaming else packet.encode()

            def holder():
                with ledger.lock:
                    held.set()
                    release.wait(8)

            def transport(_url, *, on_late_response, **_kwargs):
                sends.append(True)
                callbacks.append(on_late_response)
                yield "headers", reply
                threading.Thread(target=holder, daemon=True).start()
                if not held.wait(3):
                    raise AssertionError("ledger not held")
                threading.Event().wait(max(0, deadline - time.time()))
                raise requests.ReadTimeout("offline timeout")

            with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
                adapter = (InternStreamAdapter if streaming else InternModelAdapter)(
                    InternChatClient(timeout=6, retry=3), max_tokens=32)

            def call():
                try:
                    with bind_budget(budget):
                        operation = adapter.stream_complete if streaming else adapter.complete
                        result = operation([{"role": "user", "content": "offline"}], metadata={
                            "role": "explore", "strict_completion": True, "phase_deadline_at": deadline})
                        results.append(list(result) if streaming else result)
                except BaseException as exc:
                    failures.append(exc)
                finally:
                    done.set()

            def late():
                try:
                    callbacks[0](reply, body, .01, 2, True)
                except BaseException as exc:
                    late_errors.append(exc)

            try:
                with patch("showcase.request_transport.response_events", side_effect=transport):
                    caller = threading.Thread(target=call, daemon=True)
                    caller.start()
                    self.assertTrue(held.wait(4))
                    self.assertTrue(done.wait(max(0, deadline - time.time()) + 3))
                    self.assertEqual([], results)
                    self.assertEqual(1, len(failures))
                    self.assertIsInstance(failures[0], AdapterError)
                    self.assertEqual("timeout", failures[0].category)
                    original, = observer.attempts(budget.run_id)
                    snapshot = observer.snapshot(budget.run_id)
                    self.assertEqual(1, snapshot["unresolved_attempts"])
                    self.assertGreater(snapshot["reserved_tokens"], 0)
                    self.assertNotEqual("not_submitted", original["dispatch_status"])
                    first = threading.Thread(target=late, name="test-late-contender", daemon=True)
                    first.start()
                    self.assertTrue(contended.wait(3), "late callback did not contend with held ledger")
                    self.assertFalse(release.is_set())
                    release.set()
                    ledger.close()
                    # Both callbacks refer to the original attempt; the second races the first.
                    second = threading.Thread(target=late, name="test-late-duplicate", daemon=True)
                    second.start()
                    resume.set()
                    first.join(5)
                    second.join(5)
                    caller.join(2)
                    self.assertFalse(first.is_alive())
                    self.assertFalse(second.is_alive())
                    self.assertEqual([], late_errors)
                    self.assertEqual([True], sends)
                reopened = RunBudgetLedger(database_path=path)
                try:
                    settled, = reopened.attempts(budget.run_id)
                    final = reopened.snapshot(budget.run_id)
                    self.assertEqual(original["attempt_id"], settled["attempt_id"])
                    self.assertEqual("success", settled["status"])
                    self.assertEqual(10, settled["usage"]["total_tokens"])
                    self.assertEqual(1, final["http_attempts"])
                    self.assertEqual(10, final["charged_tokens"])
                    self.assertEqual(0, final["unresolved_attempts"])
                    self.assertEqual(0, final["reserved_tokens"])
                finally:
                    reopened.close()
            finally:
                release.set()
                resume.set()
                observer.close()
                ledger.close()


    def test_successful_accounting_remains_synchronous(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                self.check_success_waits_for_accounting(streaming)

    def check_success_waits_for_accounting(self, streaming):
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure(f"synchronous-{streaming}", RunBudgetLimits(max_runtime_seconds=10))
        entered, release, finished = (threading.Event() for _ in range(3))
        self.addCleanup(release.set)
        results, failures, sends = [], [], []

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

        usage = {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}
        choice = {"finish_reason": "stop", "delta" if streaming else "message": {"content": "ok"}}
        packet = json.dumps({"choices": [choice], "usage": usage})
        body = ("data: " + packet + "\n\ndata: [DONE]\n\n").encode() if streaming else packet.encode()

        def transport(_url, **_kwargs):
            sends.append(True)
            yield "headers", Reply()
            yield "bytes", body
            yield "complete", None

        actual_settle = ledger.settle

        def settle(run_id, attempt_id, event):
            if event.get("status") == "success":
                entered.set()
                if not release.wait(5):
                    raise AssertionError("accounting was not released")
            return actual_settle(run_id, attempt_id, event)

        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            adapter = (InternStreamAdapter if streaming else InternModelAdapter)(
                InternChatClient(timeout=6, retry=1), max_tokens=32)

        def call():
            try:
                with bind_budget(budget):
                    operation = adapter.stream_complete if streaming else adapter.complete
                    result = operation([{"role": "user", "content": "offline"}], metadata={
                        "role": "explore", "strict_completion": True})
                    results.append(list(result) if streaming else result)
            except BaseException as exc:
                failures.append(exc)
            finally:
                finished.set()

        with (patch("showcase.request_transport.response_events", side_effect=transport),
              patch.object(ledger, "settle", side_effect=settle)):
            worker = threading.Thread(target=call, daemon=True)
            worker.start()
            self.assertTrue(entered.wait(3))
            self.assertFalse(finished.wait(.15), "success returned before accounting completed")
            self.assertGreater(budget.snapshot()["reserved_tokens"], 0)
            release.set()
            self.assertTrue(finished.wait(3))
            worker.join(1)
        self.assertEqual([], failures)
        self.assertEqual(1, len(results))
        self.assertEqual([True], sends)
        self.assertEqual(10, budget.snapshot()["charged_tokens"])
        self.assertEqual(0, budget.snapshot()["reserved_tokens"])


    def test_late_retry_exhaustion_is_bounded_and_retains_review_evidence(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                self.check_late_retry_exhaustion(streaming)

    def check_late_retry_exhaustion(self, streaming):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "budget.sqlite"
            ledger = RunBudgetLedger(database_path=path)
            observer = RunBudgetLedger(database_path=path)
            budget = ledger.ensure(f"retry-exhausted-{streaming}", RunBudgetLimits(max_runtime_seconds=10))
            held, release, finished = (threading.Event() for _ in range(3))
            callbacks, sends = [], []

            class Reply:
                status_code = 200

            usage = {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}
            choice = {"finish_reason": "stop", "delta" if streaming else "message": {"content": "private"}}
            packet = json.dumps({"choices": [choice], "usage": usage})
            body = ("data: " + packet + "\n\ndata: [DONE]\n\n").encode() if streaming else packet.encode()

            def transport(_url, *, on_late_response, **_kwargs):
                callbacks.append(on_late_response)
                sends.append(True)
                raise requests.ReadTimeout("offline timeout")
                yield

            def holder():
                with ledger.lock:
                    held.set()
                    release.wait(8)

            def late():
                try:
                    callbacks[0](Reply(), body, .01, 2, True)
                finally:
                    finished.set()

            try:
                with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
                    adapter = (InternStreamAdapter if streaming else InternModelAdapter)(
                        InternChatClient(timeout=4, retry=1), max_tokens=32)
                with patch("showcase.request_transport.response_events", side_effect=transport):
                    with bind_budget(budget), self.assertRaises(AdapterError):
                        operation = adapter.stream_complete if streaming else adapter.complete
                        result = operation([{"role": "user", "content": "offline"}], metadata={
                            "role": "explore", "strict_completion": True})
                        if streaming:
                            list(result)
                original, = observer.attempts(budget.run_id)
                before = observer.snapshot(budget.run_id)
                threading.Thread(target=holder, daemon=True).start()
                self.assertTrue(held.wait(3))
                with self.assertLogs("showcase.run_budget_late", level="WARNING") as logs:
                    worker = threading.Thread(target=late, daemon=True)
                    worker.start()
                    self.assertTrue(finished.wait(3), "retry did not stop while ledger remained held")
                self.assertFalse(release.is_set())
                self.assertEqual([True], sends)
                self.assertTrue(any(budget.run_id in line and original["attempt_id"] in line
                                    and "unresolved" in line for line in logs.output))
                self.assertTrue(all("private" not in line for line in logs.output))
                self.assertEqual(before["reserved_tokens"], observer.snapshot(budget.run_id)["reserved_tokens"])
                self.assertEqual(1, observer.snapshot(budget.run_id)["unresolved_attempts"])
                self.assertEqual(original, observer.attempts(budget.run_id)[0])
                release.set()
                worker.join(2)
            finally:
                release.set()
                observer.close()
                ledger.close()


if __name__ == "__main__":
    unittest.main()
