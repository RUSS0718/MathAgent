"""Read each activity snapshot once without dropping durable stream evidence."""

import unittest
from unittest.mock import patch

from showcase.solver_harness import (
    SolverHarness,
    SolverIdentityError,
    SolverRevisionConflictError,
    SolverValidationError,
)


class StreamHistoryReadTest(unittest.TestCase):
    def test_activity_and_text_checkpoint_each_read_one_history(self):
        with SolverHarness(config={
            "max_model_calls": 3,
            "features": {"stream_recovery": True, "stream_activity": True},
        }) as harness:
            run = harness.solve("question", {"run_id": "read-once"})
            activity_reads, checkpoint_reads = [], []
            with patch.object(harness._state_store, "get_run", wraps=harness._state_store.get_run) as reads:
                def operation(request):
                    for second in (1, 2):
                        before = reads.call_count
                        request["activity_observer"]({
                            "kind": "content", "at": f"2026-11-05T00:00:0{second}Z",
                            "content_bytes": second,
                        })
                        activity_reads.append(reads.call_count - before)
                    before = reads.call_count
                    yield {"type": "text_delta", "text": "x"}
                    checkpoint_reads.append(reads.call_count - before)
                    yield {"type": "result", "result": {"assessment": "NEED_PLAN"}}

                harness.dispatch(run, operation, {
                    "run_id": run["run_id"], "role": "explore", "call_id": "read-call",
                    "problem": "question",
                })

            self.assertEqual([1, 1], activity_reads)
            self.assertEqual([1], checkpoint_reads)
            record = run["state"]["calls"]["read-call"]
            self.assertEqual("2026-11-05T00:00:01Z", record["stream_metrics"]["first_content_at"])
            self.assertEqual("2026-11-05T00:00:02Z", record["stream_metrics"]["last_content_at"])
            self.assertEqual("x", record["partial_text"])
            self.assertEqual("completed", record["status"])
            self.assertEqual(2, sum(event["type"] == "call_activity" for event in run["events"]))

    def test_snapshot_reuse_keeps_stale_revision_conflicts(self):
        with SolverHarness() as harness:
            stale = harness.solve("question", {"run_id": "stale-snapshot"})
            newer = harness.commit_event(
                stale["run_id"], expected_revision=stale["state_revision"],
                event={"event_id": "newer", "type": "checkpoint"},
            )
            with self.assertRaises(SolverRevisionConflictError):
                harness._commit_event(
                    stale["run_id"], expected_revision=stale["state_revision"],
                    event={"event_id": "stale", "type": "call_activity"}, current=stale,
                )
            current = harness.get_run(stale["run_id"])
            self.assertEqual(newer["state_revision"], current["state_revision"])
            self.assertNotIn("stale", [event["event_id"] for event in current["events"]])

    def test_snapshot_reuse_keeps_run_identity_checks(self):
        with SolverHarness() as harness:
            first = harness.solve("first", {"run_id": "first-run"})
            other = harness.solve("other", {"run_id": "other-run"})
            with self.assertRaises(SolverIdentityError):
                harness._commit_event(
                    first["run_id"], expected_revision=first["state_revision"],
                    event={"event_id": "wrong-run", "type": "call_activity"}, current=other,
                )
            self.assertEqual(first["state_revision"], harness.get_run(first["run_id"])["state_revision"])

    def test_snapshot_reuse_keeps_terminal_business_state_frozen(self):
        with SolverHarness(config={"features": {"stream_recovery": True}}) as harness:
            run = harness.solve("question", {"run_id": "terminal-snapshot"})
            terminal = harness.commit_event(
                run["run_id"], expected_revision=run["state_revision"],
                event={"event_id": "stop", "type": "run_finished"},
                state_updates={"phase": "TERMINAL", "status": "partial_aborted", "final_response": "Stopped"},
            )
            with self.assertRaises(SolverValidationError):
                harness._commit_event(
                    run["run_id"], expected_revision=terminal["state_revision"],
                    event={"event_id": "rewrite", "type": "call_activity"},
                    state_updates={"final_response": "Changed"}, current=terminal,
                )
            self.assertEqual("Stopped", harness.get_run(run["run_id"])["state"]["final_response"])


if __name__ == "__main__":
    unittest.main()
