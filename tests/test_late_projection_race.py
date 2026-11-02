"""Deterministic regression for late-settlement attempt projection ordering."""

import json
import os
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import requests

import llm_client
from llm_client import InternChatClient
from showcase.adapters import AdapterError, InternModelAdapter
from showcase.attempt_projection import bind_attempt_projection as bind_projection
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget


class LateProjectionRaceTest(unittest.TestCase):
    """Keep the adapter's public attempt aligned with its ledger after a late callback."""

    def test_callback_holding_attempt_lock_races_projection_binding(self):
        """Binding blocks on callback settlement, then publishes the settled attempt."""
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        run_budget = ledger.ensure(
            "late-projection-race", RunBudgetLimits(max_runtime_seconds=60)
        )
        call_budget = run_budget.model_call(role="solver")
        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-test-key"}):
            client = InternChatClient(timeout=2, retry=1)
        client.api_base = "http://127.0.0.1/never-requested"
        adapter = InternModelAdapter(client, max_tokens=16)

        adapter_thread_id = threading.get_ident()
        callback_thread_id = []
        callback_in_critical_section = threading.Event()
        projection_bind_blocked = threading.Event()
        callback_handler_finished = threading.Event()
        projection_binding_finished = threading.Event()
        callback_finished = threading.Event()
        callback_errors = []
        callback_holder = []
        callback_threads = []
        response = requests.Response()
        response.status_code = 200
        body = json.dumps(
            {
                "id": "response-late-race",
                "model": "intern-s2",
                "choices": [
                    {"message": {"content": "answer"}, "finish_reason": "stop"}
                ],
                "usage": {
                    "prompt_tokens": 7,
                    "completion_tokens": 3,
                    "total_tokens": 10,
                },
            }
        ).encode()
        native_rlock = threading.RLock

        class ControlledAttemptLock:
            """Expose the real lock interleaving without changing callback behavior."""

            def __init__(self):
                self._lock = native_rlock()
                self._depth = threading.local()

            def __enter__(self):
                thread_id = threading.get_ident()
                if (
                    thread_id == adapter_thread_id
                    and callback_in_critical_section.is_set()
                ):
                    if not self._lock.acquire(blocking=False):
                        projection_bind_blocked.set()
                        self._lock.acquire()
                    else:
                        self._lock.release()
                        raise AssertionError("projection binding did not contend on callback lock")
                else:
                    self._lock.acquire()

                depth = getattr(self._depth, "value", 0) + 1
                self._depth.value = depth
                if callback_thread_id and thread_id == callback_thread_id[0] and depth == 1:
                    callback_in_critical_section.set()
                    if not projection_bind_blocked.wait(timeout=5):
                        self._depth.value = depth - 1
                        self._lock.release()
                        raise AssertionError("projection binding never contended on callback lock")
                return self

            def __exit__(self, _exception_type, _exception, _traceback):
                thread_id = threading.get_ident()
                depth = self._depth.value
                if callback_thread_id and thread_id == callback_thread_id[0] and depth == 1:
                    callback_handler_finished.set()
                self._depth.value = depth - 1
                self._lock.release()

        def fake_response_events(_url, *, on_late_response, **_kwargs):
            callback_holder.append(on_late_response)
            raise requests.ReadTimeout("simulated_deadline")

        def bind_during_settlement(source, projection):
            def deliver_late_response():
                callback_thread_id.append(threading.get_ident())
                try:
                    callback_holder[0](response, body, 0.01, 0.02, True)
                except BaseException as exc:
                    callback_errors.append(exc)
                finally:
                    callback_finished.set()

            callback_thread = threading.Thread(target=deliver_late_response, daemon=True)
            callback_threads.append(callback_thread)
            callback_thread.start()
            if not callback_in_critical_section.wait(timeout=5):
                raise AssertionError("late callback did not acquire its attempt lock")

            bind_projection(source, projection)
            projection_binding_finished.set()

        with (
            patch.object(
                llm_client,
                "threading",
                SimpleNamespace(RLock=ControlledAttemptLock),
            ),
            patch("showcase.request_transport.response_events", side_effect=fake_response_events),
            patch(
                "showcase.adapters.bind_attempt_projection",
                side_effect=bind_during_settlement,
            ),
        ):
            with bind_budget(call_budget):
                with self.assertRaises(AdapterError) as raised:
                    adapter.complete(
                        [{"role": "user", "content": "offline test"}],
                        metadata={"role": "solver"},
                    )

        for callback_thread in callback_threads:
            callback_thread.join(timeout=5)
            self.assertFalse(callback_thread.is_alive())
        self.assertEqual([], callback_errors)
        self.assertTrue(projection_bind_blocked.is_set())
        self.assertTrue(callback_handler_finished.is_set())
        self.assertTrue(projection_binding_finished.is_set())
        self.assertTrue(callback_finished.is_set())

        public_attempt, = raised.exception.request_attempts
        ledger_attempt, = ledger.attempts("late-projection-race")
        self.assertEqual("success", public_attempt["status"])
        self.assertEqual(public_attempt["attempt_id"], ledger_attempt["attempt_id"])
        self.assertEqual(public_attempt["status"], ledger_attempt["status"])
        self.assertEqual(public_attempt["usage"], ledger_attempt["usage"])
        self.assertEqual("response-late-race", public_attempt["provider_request_id"])


if __name__ == "__main__":
    unittest.main()
