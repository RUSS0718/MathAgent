"""Deadline detachment must not wait for a preempted transport lock."""

import json
import os
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import requests

from llm_client import InternChatClient
from showcase.adapters import AdapterError, InternModelAdapter
from showcase.request_transport import DeadlineNotSubmitted, response_events
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget


class HeldReaderLock:
    def __init__(self, targeted, entered, release):
        self.lock = threading.Lock()
        self.targeted, self.entered, self.release_event = targeted, entered, release

    def acquire(self, *args, **kwargs):
        return self.lock.acquire(*args, **kwargs)

    def release(self):
        self.lock.release()

    def __enter__(self):
        self.lock.acquire()
        if self.targeted and threading.current_thread().name.startswith("showcase-http-reader"):
            self.entered.set()
            if not self.release_event.wait(6):
                raise AssertionError("reader lock not released")
        return self

    def __exit__(self, *_args):
        self.lock.release()


def gated_threading(lock_index, entered, release):
    created = []

    def lock_factory():
        item = HeldReaderLock(len(created) == lock_index, entered, release)
        created.append(item)
        return item

    return SimpleNamespace(Lock=lock_factory, Event=threading.Event,
                           Thread=threading.Thread, current_thread=threading.current_thread)


class TransportLockDeadlineTest(unittest.TestCase):
    def test_busy_dispatch_gate_returns_unknown_without_waiting_or_sending(self):
        entered, release, finished = (threading.Event() for _ in range(3))
        self.addCleanup(release.set)
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("dispatch-gate-busy", RunBudgetLimits(max_runtime_seconds=8))
        deadline = time.time() + .5
        failures, sends = [], []
        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            adapter = InternModelAdapter(InternChatClient(timeout=3, retry=1), max_tokens=32)

        def run():
            try:
                with bind_budget(budget):
                    adapter.complete([{"role": "user", "content": "offline"}],
                                     metadata={"role": "explore", "phase_deadline_at": deadline})
            except BaseException as exc:
                failures.append(exc)
            finally:
                finished.set()

        with (patch("showcase.request_transport.threading", gated_threading(1, entered, release)),
              patch("showcase.request_transport.requests.post", side_effect=lambda *a, **k: sends.append(1))):
            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            self.assertTrue(entered.wait(3))
            self.assertTrue(finished.wait(2), "timeout waited for dispatch gate")
            self.assertFalse(release.is_set())
            self.assertEqual(1, len(failures))
            self.assertIsInstance(failures[0], AdapterError)
            self.assertEqual("timeout", failures[0].category)
            attempt, = ledger.attempts(budget.run_id)
            self.assertNotEqual("not_submitted", attempt.get("dispatch_status"))
            self.assertEqual(1, budget.snapshot()["unresolved_attempts"])
            self.assertGreater(budget.snapshot()["reserved_tokens"], 0)
            release.set()
            worker.join(1)
            time.sleep(.05)
            self.assertEqual([], sends)

    def test_busy_late_lock_returns_then_settles_complete_reply_once(self):
        entered, release, finished, settled = (threading.Event() for _ in range(4))
        self.addCleanup(release.set)
        deadline = time.monotonic() + .5
        errors, callbacks = [], []
        body = json.dumps({"ok": True}).encode()

        class Reply:
            def iter_content(self, chunk_size=1):
                yield body

            def close(self):
                pass

        def late(_response, received, *_args):
            callbacks.append(received)
            settled.set()

        def run():
            try:
                events = response_events("https://offline.invalid", deadline=deadline, timeout=3,
                                         on_late_response=late)
                self.assertEqual("headers", next(events)[0])
                entered.wait(3)
                time.sleep(max(0, deadline - time.monotonic()) + .05)
                next(events)
            except BaseException as exc:
                errors.append(exc)
            finally:
                finished.set()

        with (patch("showcase.request_transport.threading", gated_threading(0, entered, release)),
              patch("showcase.request_transport.requests.post", return_value=Reply())):
            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            self.assertTrue(entered.wait(3))
            self.assertTrue(finished.wait(2), "timeout waited for late lock")
            self.assertFalse(release.is_set())
            self.assertEqual(1, len(errors))
            self.assertIsInstance(errors[0], requests.ReadTimeout)
            self.assertNotIsInstance(errors[0], DeadlineNotSubmitted)
            release.set()
            self.assertTrue(settled.wait(3))
            worker.join(1)
            time.sleep(.05)
        self.assertEqual([body], callbacks)


if __name__ == "__main__":
    unittest.main()
