"""Metered deadlines retain the ledger UTC identity across clock phases."""

import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import requests

from llm_client import InternChatClient, ChatClientError
from showcase.adapters import AdapterError, InternStreamAdapter
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget


class MeteredAbsoluteDeadlineTest(unittest.TestCase):
    def test_clock_rollback_latches_expiration_without_extending_wait(self):
        from showcase.deadline_clock import guarded_utc_clock
        from showcase.request_transport import response_events, DeadlineNotSubmitted
        from showcase.processing_deadline import process_before_deadline

        values = iter([100., 99., 101., 102., 103., 104.])
        clock = guarded_utc_clock(lambda: next(values))
        self.assertEqual(100., clock())
        self.assertEqual(float("inf"), clock())
        self.assertEqual(float("inf"), clock())
        with patch("showcase.request_transport.requests.post") as post:
            with self.assertRaises(DeadlineNotSubmitted):
                list(response_events("https://offline.invalid", deadline=110., timeout=10.,
                                     clock=clock))
            post.assert_not_called()
        with self.assertRaises(requests.ReadTimeout):
            process_before_deadline(lambda: "late", 110., lambda *_: None,
                                    clock=lambda: float("inf"))

    def test_scoped_deadline_is_not_reanchored_after_a_ledger_read(self):
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("scoped", RunBudgetLimits())
        original = budget.snapshot()["deadline_at"]
        call = budget.model_call("explore", deadline_at=original - 1)
        self.assertEqual(original - 1, call.absolute_deadline())
        self.assertEqual(original, budget.snapshot()["deadline_at"])

    def test_clock_phase_cannot_move_the_original_budget_deadline(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                ledger = RunBudgetLedger()
                self.addCleanup(ledger.close)
                budget = ledger.ensure(str(streaming), RunBudgetLimits())
                absolute = budget.snapshot()["deadline_at"]
                # Both duration clocks have a deliberately unrelated phase.
                wall = [absolute - .08]
                clocks = SimpleNamespace(time=lambda: wall[0], monotonic=lambda: 10.,
                                         perf_counter=lambda: 20., sleep=time.sleep)
                sent = []

                def transport(_url, *, deadline, clock=None, **kwargs):
                    sent.append(deadline)
                    self.assertEqual(absolute, deadline)
                    self.assertLess(clock(), deadline)
                    wall[0] = absolute  # The first expired UTC observation.
                    self.assertEqual(deadline, clock())
                    raise requests.ReadTimeout("offline deadline")
                    yield

                with patch.dict("os.environ", {"INTERN_API_KEY": "offline-only"}):
                    client = InternChatClient(timeout=600, retry=1)
                with (patch("llm_client.time", clocks), patch("showcase.adapters.time", clocks),
                      patch("showcase.request_transport.response_events", side_effect=transport)):
                    if streaming:
                        with bind_budget(budget), self.assertRaises(AdapterError):
                            list(InternStreamAdapter(client).stream_complete(
                                [{"role": "user", "content": "offline"}], metadata={"role": "explore"}))
                    else:
                        call = budget.model_call("explore")
                        with self.assertRaises(ChatClientError):
                            client.chat_response([{"role": "user", "content": "offline"}],
                                                 _attempt_budget=call)
                self.assertEqual([absolute], sent)
                self.assertEqual(absolute, budget.snapshot()["deadline_at"])


if __name__ == "__main__":
    unittest.main()
