"""Offline race after logical dispatch and before the final transport check."""

import inspect
import os
import threading
import time
import unittest
from unittest.mock import patch

from llm_client import InternChatClient
from showcase import request_transport
from showcase.adapters import AdapterError, InternModelAdapter, InternStreamAdapter
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget


class DispatchRecheckTest(unittest.TestCase):
    def test_expired_committed_reader_skips_post_but_stays_unconfirmed(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                self.check_committed_reader(streaming)

    def check_committed_reader(self, streaming):
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure(f"dispatch-recheck-{streaming}", RunBudgetLimits(max_runtime_seconds=8))
        parked, release, reader_done = (threading.Event() for _ in range(3))
        self.addCleanup(release.set)
        source, first = inspect.getsourcelines(request_transport.response_events)
        # The lock has been released and dispatch_started assigned when this line executes.
        pause_line = next(first + i for i, line in enumerate(source)
                          if "if not loopback_only and not provider_endpoint_only:" in line)
        deadline = time.time() + 1
        sends = []

        def trace(frame, event, arg):
            if frame.f_code.co_name == "read_response":
                if event == "line" and frame.f_lineno == pause_line:
                    parked.set()
                    if not release.wait(5):
                        raise AssertionError("reader was not released")
                elif event == "return":
                    reader_done.set()
            return trace

        def post(*_args, **_kwargs):
            sends.append(True)
            raise OSError("offline fake")

        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            adapter = (InternStreamAdapter if streaming else InternModelAdapter)(
                InternChatClient(timeout=3, retry=1), max_tokens=32)
        threading.settrace(trace)
        try:
            with patch("showcase.request_transport.requests.post", side_effect=post):
                with bind_budget(budget), self.assertRaises(AdapterError) as caught:
                    operation = adapter.stream_complete if streaming else adapter.complete
                    result = operation([{"role": "user", "content": "offline"}],
                                       metadata={"role": "explore", "phase_deadline_at": deadline})
                    if streaming:
                        list(result)
                self.assertTrue(parked.is_set())
                self.assertEqual("timeout", caught.exception.category)
                before, = ledger.attempts(budget.run_id)
                summary = budget.snapshot()
                self.assertEqual("reserved_dispatch_unconfirmed", before["dispatch_status"])
                self.assertEqual(1, summary["unresolved_attempts"])
                self.assertGreater(summary["reserved_tokens"], 0)
                release.set()
                self.assertTrue(reader_done.wait(3))
                self.assertEqual([], sends)
                self.assertEqual(before, ledger.attempts(budget.run_id)[0])
                self.assertEqual(summary["reserved_tokens"], budget.snapshot()["reserved_tokens"])
        finally:
            release.set()
            threading.settrace(None)


if __name__ == "__main__":
    unittest.main()
