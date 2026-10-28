"""Competing stale snapshots at the public call-repair boundary."""

import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from showcase.adapters import InternModelAdapter
from showcase.run_budget import RunBudget, RunBudgetLedger, RunBudgetLimits, bind_budget
from showcase.solver_harness import SolverHarness
from showcase.solver_harness.calls import CallInterrupted
from showcase.solver_harness.intern_port import InternModelPort, InternPortError
from showcase.solver_harness.serialization_repair import repair_failure
from tests.test_solver_harness_intern import FakeClient


class FormatRepairClaimTest(unittest.TestCase):
    def test_f08_competing_stale_claims_notify_and_dispatch_once(self):
        barrier = threading.Barrier(2)

        class ScheduledBudget(RunBudget):
            """Schedule real ledger reads so both callers hold the same revision."""
            seen = threading.local()

            def snapshot(self):
                if not getattr(self.seen, "arrived", False):
                    self.seen.arrived = True
                    barrier.wait(5)
                return super().snapshot()

        events = []
        config = {"features": {"serialization_repair": True, "stream_recovery": True},
                  "max_model_calls": 8}
        value = {"argument": "For every n, x=2.", "claims": [], "blocked": False}
        usage = {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}
        client = FakeClient([{"content": text, "finish_reason": "stop", "usage": usage}
                             for text in ("```json\n" + json.dumps(value) + "\n```", json.dumps(value))])
        with tempfile.TemporaryDirectory() as directory, SolverHarness(
                config=config, event_observer=lambda _run, event: events.append(event)) as harness:
            initial = harness.solve("private problem", {"run_id": "run-a"})
            port = InternModelPort(InternModelAdapter(client), original_problem="private problem",
                                   restricted_reply_dir=Path(directory) / "private")
            request = {"run_id": "run-a", "call_id": "root", "role": "reasoner",
                       "problem": "private problem", "problem_hash": initial["state"]["problem_hash"],
                       "serialization_repair": True}
            with self.assertRaises(InternPortError) as error:
                port.complete(request)
            failed = {"call_id": "root", "role": "reasoner", "run_id": "run-a",
                      "status": "protocol_failed", "serialization_eligible": True,
                      "response_ref": error.exception.response_ref, "request_revision": initial["state_revision"],
                      "request": request}
            harness.commit_event("run-a", expected_revision=initial["state_revision"],
                event={"event_id": "known-failure", "type": "call_audit"},
                state_updates={"calls": {"root": failed}})
            ledger = RunBudgetLedger()
            self.addCleanup(ledger.close)
            ledger.ensure("run-a", RunBudgetLimits(max_model_calls=8, max_http_attempts=8))
            budget = ScheduledBudget(ledger, "run-a")

            def compete(_index):
                local = harness.get_run("run-a")
                with bind_budget(budget):
                    try:
                        return repair_failure(harness, local, failed, port.complete, request)
                    except CallInterrupted:
                        return None

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(compete, range(2)))
            reservations = [event for event in events if event["type"] == "serialization_repair_reserved"]
            self.assertEqual(1, len(reservations), "idempotent event replay gave a second claimant ownership")
            self.assertEqual(1, sum(result == value for result in results))
            self.assertEqual(2, len(client.requests))
            self.assertEqual({"root": "root:serialization-1"},
                             harness.get_run("run-a")["state"]["serialization_repairs"])


if __name__ == "__main__":
    unittest.main()
