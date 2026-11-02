"""Issue #98: an occupied persisted ledger must not hold a timed-out call."""

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


class LedgerLockDeadlineTest(unittest.TestCase):
    def test_timeout_returns_while_ledger_locked_and_late_reply_settles_original(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                self.check_locked_timeout(streaming)

    def check_locked_timeout(self, streaming):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "ledger.sqlite"
            ledger = RunBudgetLedger(database_path=database)
            observer = RunBudgetLedger(database_path=database)
            release = threading.Event()
            try:
                budget = ledger.ensure(f"locked-{streaming}", RunBudgetLimits(max_runtime_seconds=12))
                held, finished, late_started, late_finished = (threading.Event() for _ in range(4))
                failures, results, callbacks, sends = [], [], [], []
                deadline = time.time() + 1.5

                class Reply:
                    status_code = 200

                    def raise_for_status(self):
                        pass

                reply = Reply()
                packet = {"choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
                          "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}
                stream_packet = {"choices": [{"finish_reason": "stop", "delta": {"content": "ok"}}],
                                 "usage": packet["usage"]}
                body = (("data: " + json.dumps(stream_packet) + "\n\ndata: [DONE]\n\n").encode()
                        if streaming else json.dumps(packet).encode())

                def hold_ledger():
                    with ledger.lock:
                        held.set()
                        release.wait(8)

                def events(_url, *, on_late_response, **_kwargs):
                    sends.append(True)
                    callbacks.append(on_late_response)
                    yield "headers", reply
                    threading.Thread(target=hold_ledger, daemon=True).start()
                    if not held.wait(3):
                        raise AssertionError("ledger fixture lock not acquired")
                    threading.Event().wait(max(0, deadline - time.time()))
                    raise requests.ReadTimeout("offline dispatched timeout")

                with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
                    client = InternChatClient(timeout=8, retry=3)
                adapter = (InternStreamAdapter if streaming else InternModelAdapter)(client, max_tokens=32)

                def run():
                    try:
                        with bind_budget(budget):
                            invoke = adapter.stream_complete if streaming else adapter.complete
                            result = invoke([{"role": "user", "content": "offline"}],
                                            metadata={"role": "explore", "strict_completion": True,
                                                      "phase_deadline_at": deadline})
                            results.append(list(result) if streaming else result)
                    except BaseException as exc:
                        failures.append(exc)
                    finally:
                        finished.set()

                def late():
                    late_started.set()
                    try:
                        callbacks[0](reply, body, .01, 2, True)
                    finally:
                        late_finished.set()

                with patch("showcase.request_transport.response_events", side_effect=events):
                    worker = threading.Thread(target=run, daemon=True)
                    worker.start()
                    try:
                        self.assertTrue(held.wait(4))
                        self.assertTrue(finished.wait(max(0, deadline - time.time()) + 2),
                                        "timeout waited for the occupied ledger lock")
                        self.assertFalse(release.is_set())
                        pending, = observer.attempts(budget.run_id)
                        before = observer.snapshot(budget.run_id)
                        self.assertEqual(1, before["unresolved_attempts"])
                        self.assertGreater(before["reserved_tokens"], 0)
                        self.assertNotEqual("not_submitted", pending.get("dispatch_status"))
                        self.assertIsNone(pending["usage"]["total_tokens"])
                        late_worker = threading.Thread(target=late, daemon=True)
                        late_worker.start()
                        self.assertTrue(late_started.wait(2))
                    finally:
                        release.set()
                    self.assertTrue(late_finished.wait(5))
                    worker.join(2)
                    late_worker.join(2)
                    until = time.monotonic() + 4
                    while observer.snapshot(budget.run_id)["unresolved_attempts"] and time.monotonic() < until:
                        time.sleep(.01)
                    after, = observer.attempts(budget.run_id)
                    summary = observer.snapshot(budget.run_id)
                self.assertEqual([], results)
                self.assertEqual(1, len(failures))
                self.assertIsInstance(failures[0], AdapterError)
                self.assertEqual("timeout", failures[0].category)
                self.assertEqual([True], sends)
                self.assertEqual(pending["attempt_id"], after["attempt_id"])
                self.assertEqual("success", after["status"])
                self.assertEqual(10, after["usage"]["total_tokens"])
                self.assertEqual(0, summary["unresolved_attempts"])
                self.assertEqual(0, summary["reserved_tokens"])
            finally:
                release.set()
                observer.close()
                ledger.close()


if __name__ == "__main__":
    unittest.main()
