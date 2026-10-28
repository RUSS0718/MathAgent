"""Issue #98: expiry during reservation must not dispatch a provider request."""

import inspect
import json
import os
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from llm_client import InternChatClient
from showcase import request_transport
from showcase.adapters import AdapterError, InternModelAdapter, InternStreamAdapter
from showcase.request_transport import DeadlineNotSubmitted, response_events
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget
from showcase.run_control import RunStopped


class DispatchBoundaryTest(unittest.TestCase):
    def test_reservation_wait_crossing_each_deadline_does_not_dispatch(self):
        for stream in (False, True):
            for kind in ("request", "phase", "batch", "run"):
                with self.subTest(stream=stream, deadline=kind):
                    self.check_expired_reservation(stream, kind)

    def test_reader_scheduled_after_deadline_never_dispatches(self):
        waiting, release, finished, dispatched = (threading.Event() for _ in range(4))
        self.addCleanup(release.set)

        def delayed_thread(*, target, **kwargs):
            def run():
                waiting.set()
                if release.wait(3):
                    target()
                finished.set()
            return threading.Thread(target=run, **kwargs)

        fake_threading = SimpleNamespace(Thread=delayed_thread, Event=threading.Event,
                                         Lock=threading.Lock, current_thread=threading.current_thread)
        with (patch("showcase.request_transport.threading", fake_threading),
              patch("showcase.request_transport.requests.post", side_effect=lambda *_a, **_k: dispatched.set())):
            events = response_events("http://127.0.0.1", deadline=time.monotonic() + .15, timeout=2)
            with self.assertRaises(DeadlineNotSubmitted) as caught:
                next(events)
            self.assertEqual("DeadlineNotSubmitted", type(caught.exception).__name__)
            self.assertTrue(waiting.is_set())
            release.set()
            self.assertTrue(finished.wait(2))
        self.assertFalse(dispatched.is_set())
    def test_closing_stream_after_processing_deadline_settles_buffered_reply(self):
        reader_done, callback_done = threading.Event(), threading.Event()
        callbacks = []

        class Reply:
            status_code = 200

            def iter_content(self, chunk_size=1):
                yield b"complete response"
                reader_done.set()

            def close(self):
                pass

        def late(*args):
            callbacks.append(args)
            callback_done.set()

        with patch("showcase.request_transport.requests.post", return_value=Reply()):
            deadline = time.monotonic() + .35
            events = response_events("http://127.0.0.1", deadline=deadline, timeout=2,
                                     on_late_response=late)
            self.assertEqual("headers", next(events)[0])
            self.assertEqual(("bytes", b"complete response"), next(events))
            self.assertTrue(reader_done.wait(2))
            time.sleep(max(0, deadline - time.monotonic()) + .05)
            events.close()
            self.assertTrue(callback_done.wait(2))
        self.assertEqual(1, len(callbacks))
        self.assertEqual(b"complete response", callbacks[0][1])
        self.assertTrue(callbacks[0][4])
    def test_dispatch_commit_without_transport_observation_stays_unconfirmed(self):
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("dispatch-unconfirmed", RunBudgetLimits(max_runtime_seconds=8))
        parked, release, posted = (threading.Event() for _ in range(3))
        self.addCleanup(release.set)
        source, first = inspect.getsourcelines(request_transport.response_events)
        post_line = next(first + i for i, line in enumerate(source) if "response = post(" in line)
        deadline = time.time() + .5

        def trace(frame, event, arg):
            if frame.f_code.co_name == "read_response" and event == "line" and frame.f_lineno == post_line:
                parked.set()
                if not release.wait(3):
                    raise AssertionError("reader was not released")
            return trace

        def fake_post(*_args, **_kwargs):
            posted.set()
            raise OSError("offline")

        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            adapter = InternModelAdapter(InternChatClient(timeout=2, retry=1), max_tokens=32)
        threading.settrace(trace)
        try:
            with patch("showcase.request_transport.requests.post", side_effect=fake_post):
                with bind_budget(budget), self.assertRaises(AdapterError) as caught:
                    adapter.complete([{"role": "user", "content": "offline"}],
                                     metadata={"role": "explore", "phase_deadline_at": deadline})
                self.assertTrue(parked.is_set())
                self.assertEqual("timeout", caught.exception.category)
                attempt, = ledger.attempts(budget.run_id)
                self.assertEqual("error", attempt["status"])
                self.assertEqual("reserved_dispatch_unconfirmed", attempt["dispatch_status"])
                self.assertEqual(1, budget.snapshot()["unresolved_attempts"])
                self.assertGreater(budget.snapshot()["reserved_tokens"], 0)
                release.set()
                posted.wait(.5)
        finally:
            release.set()
            threading.settrace(None)
    def check_expired_reservation(self, stream, kind):
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        absolute = time.time() + .35
        budget = ledger.ensure(f"{stream}-{kind}", RunBudgetLimits(max_runtime_seconds=8),
                               deadline_at=absolute if kind == "run" else None)
        metadata = {"role": "explore", "strict_completion": True}
        if kind in {"phase", "batch"}:
            metadata[f"{kind}_deadline_at"] = absolute
        if kind == "request":
            metadata["timeout_seconds"] = .25
        reserved, release, dispatched, finished = (threading.Event() for _ in range(4))
        self.addCleanup(release.set)
        original_reserve = ledger.reserve
        outcome = []

        def slow_reserve(run_id, action_kind, **kwargs):
            result = original_reserve(run_id, action_kind, **kwargs)
            if action_kind == "http":
                reserved.set()
                if not release.wait(5):
                    raise AssertionError("reservation was not released")
            return result

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

            def iter_content(self, chunk_size=1):
                yield json.dumps({"choices": [{"finish_reason": "stop", "message": {
                    "content": "unexpected"}}], "usage": {"prompt_tokens": 7,
                    "completion_tokens": 3, "total_tokens": 10}}).encode()

            def close(self):
                pass

        def post(*_args, **_kwargs):
            dispatched.set()
            return Reply()

        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            client = InternChatClient(timeout=4, retry=1)
        adapter = (InternStreamAdapter if stream else InternModelAdapter)(client, max_tokens=32)

        def run():
            try:
                with bind_budget(budget):
                    result = adapter.stream_complete if stream else adapter.complete
                    value = result([{"role": "user", "content": "offline"}], metadata=metadata)
                    outcome.append(list(value) if stream else value)
            except BaseException as exc:
                outcome.append(exc)
            finally:
                finished.set()

        with (patch.object(ledger, "reserve", side_effect=slow_reserve),
              patch("showcase.request_transport.requests.post", side_effect=post)):
            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            self.assertTrue(reserved.wait(3))
            time.sleep(max(0, absolute - time.time()) + .12)
            release.set()
            self.assertTrue(finished.wait(3))
            worker.join(1)
            self.assertFalse(dispatched.wait(.1), "provider must not be dispatched after expiry")
        self.assertEqual(1, len(outcome))
        self.assertIsInstance(outcome[0], (AdapterError, RunStopped))
        snapshot = budget.snapshot()
        attempts = ledger.attempts(budget.run_id)
        self.assertEqual(1, snapshot["http_attempts"])
        self.assertEqual(0, snapshot["unresolved_attempts"])
        self.assertEqual(0, snapshot["reserved_tokens"])
        self.assertEqual("error", attempts[0]["status"])
        self.assertEqual("not_submitted", attempts[0]["dispatch_status"])


if __name__ == "__main__":
    unittest.main()