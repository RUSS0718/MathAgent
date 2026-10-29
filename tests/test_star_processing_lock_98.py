"""Issue #98: a preempted processing handoff must not hold the caller."""

import json
import os
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import AdapterError, InternModelAdapter
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget


class ProcessingHandoffLockTest(unittest.TestCase):
    def test_preempted_handoff_returns_before_release_and_settles_original_attempt(self):
        entered, release, finished, settled = (threading.Event() for _ in range(4))
        self.addCleanup(release.set)
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("processing-gate-busy", RunBudgetLimits(max_runtime_seconds=15))
        deadline_at = []
        body = json.dumps({
            "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        }).encode()
        failures, results, sends, settlements = [], [], [], []

        class HeldProcessingLock:
            def __init__(self):
                self.lock = threading.Lock()

            def acquire(self, *args, **kwargs):
                return self.lock.acquire(*args, **kwargs)

            def release(self):
                self.lock.release()

            def __enter__(self):
                self.lock.acquire()
                if threading.current_thread().name == "showcase-response-processing":
                    entered.set()
                    if not release.wait(10):
                        raise AssertionError("processing handoff not released")
                return self

            def __exit__(self, *_args):
                self.lock.release()

        fake_threading = SimpleNamespace(Lock=HeldProcessingLock, Event=threading.Event,
                                         Thread=threading.Thread)

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

        def events(*_args, **_kwargs):
            sends.append(True)
            yield "headers", Reply()
            yield "bytes", body
            yield "complete", None

        original_settle = RunBudgetLedger.settle

        def observe_settlement(ledger, run_id, attempt_id, event):
            outcome = original_settle(ledger, run_id, attempt_id, event)
            if event.get("status") == "success":
                settlements.append(attempt_id)
                settled.set()
            return outcome

        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            adapter = InternModelAdapter(InternChatClient(timeout=8, retry=1), max_tokens=32)

        def run():
            try:
                with bind_budget(budget):
                    deadline_at.append(time.time() + 3)
                    results.append(adapter.complete(
                        [{"role": "user", "content": "offline"}],
                        metadata={"role": "explore", "phase_deadline_at": deadline_at[0],
                                  "strict_completion": True},
                    ))
            except BaseException as exc:
                failures.append(exc)
            finally:
                finished.set()

        with (patch("showcase.processing_deadline.threading", fake_threading),
              patch("showcase.request_transport.response_events", side_effect=events),
              patch.object(RunBudgetLedger, "settle", observe_settlement)):
            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            try:
                self.assertTrue(entered.wait(5), "processing did not reach the handoff")
                self.assertTrue(finished.wait(max(0, deadline_at[0] - time.time()) + 3),
                                "caller waited for the preempted processing lock")
                self.assertFalse(release.is_set())
                pending, = ledger.attempts(budget.run_id)
                self.assertEqual(1, budget.snapshot()["unresolved_attempts"])
                self.assertGreater(budget.snapshot()["reserved_tokens"], 0)
            finally:
                release.set()
            self.assertTrue(settled.wait(4), "late original attempt was not settled")
            worker.join(2)
            attempt, = ledger.attempts(budget.run_id)
        self.assertEqual([], results)
        self.assertEqual(1, len(failures))
        self.assertIsInstance(failures[0], AdapterError)
        self.assertEqual("timeout", failures[0].category)
        self.assertEqual([True], sends)
        self.assertEqual([pending["attempt_id"]], settlements)
        self.assertEqual(pending["attempt_id"], attempt["attempt_id"])
        self.assertEqual("success", attempt["status"])
        self.assertEqual(10, attempt["usage"]["total_tokens"])
        self.assertEqual(0, budget.snapshot()["unresolved_attempts"])


if __name__ == "__main__":
    unittest.main()
