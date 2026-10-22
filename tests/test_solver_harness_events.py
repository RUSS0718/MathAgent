"""Public Solver Harness event and revision contracts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from showcase.solver_harness import (
    SolverEventConflictError,
    SolverHarness,
    SolverRevisionConflictError,
    SolverValidationError,
)


class SolverHarnessEventTest(unittest.TestCase):
    def test_stale_revision_does_not_overwrite_a_successful_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "showcase.sqlite3"
            with (
                SolverHarness(database_path=database_path) as harness,
                SolverHarness(database_path=database_path) as stale_harness,
            ):
                initial = harness.solve("题目", {"run_id": "solver-cas"})
                stale_snapshot = stale_harness.solve("题目", {"run_id": "solver-cas"})
                expected_revision = initial["state_revision"]
                self.assertEqual(expected_revision, stale_snapshot["state_revision"])

                committed = harness.commit_event(
                    "solver-cas",
                    expected_revision=expected_revision,
                    event={"event_id": "winner", "type": "plan_selected"},
                    state_updates={"phase": "PLAN"},
                )

                self.assertEqual(1, committed["state_revision"])
                self.assertEqual(committed["state_revision"], committed["state"]["state_revision"])
                self.assertEqual("PLAN", committed["state"]["phase"])
                self.assertEqual(
                    committed["state_revision"], committed["events"][-1]["state_revision"]
                )

                with self.assertRaises(SolverRevisionConflictError):
                    stale_harness.commit_event(
                        "solver-cas",
                        expected_revision=expected_revision,
                        event={"event_id": "stale", "type": "plan_rejected"},
                        state_updates={"phase": "EXPLORE"},
                    )

                recovered = harness.get_run("solver-cas")
                self.assertEqual(committed, recovered)
                self.assertEqual(2, len(recovered["events"]))

    def test_replaying_the_same_event_does_not_add_a_revision_or_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "showcase.sqlite3"
            with SolverHarness(database_path=database_path) as harness:
                initial = harness.solve("题目", {"run_id": "solver-idempotent"})
                event = {"event_id": "plan-1", "type": "plan_selected", "summary": "选择计划"}
                updates = {"phase": "PLAN", "plan_version": 1}

                first = harness.commit_event(
                    "solver-idempotent",
                    expected_revision=initial["state_revision"],
                    event=event,
                    state_updates=updates,
                )
                replay = harness.commit_event(
                    "solver-idempotent",
                    expected_revision=initial["state_revision"],
                    event=event,
                    state_updates=updates,
                )

                self.assertEqual(first, replay)
                self.assertEqual(1, replay["state_revision"])
                self.assertEqual(2, len(replay["events"]))
                self.assertEqual(1, replay["events"][-1]["state_revision"])
                self.assertNotIn("_request_hash", repr(replay["events"]))

    def test_reusing_an_event_id_with_a_different_payload_fails_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "showcase.sqlite3"
            with SolverHarness(database_path=database_path) as harness:
                initial = harness.solve("题目", {"run_id": "solver-event-conflict"})
                harness.commit_event(
                    "solver-event-conflict",
                    expected_revision=initial["state_revision"],
                    event={"event_id": "event-1", "type": "plan_selected"},
                    state_updates={"phase": "PLAN"},
                )
                committed = harness.get_run("solver-event-conflict")

                with self.assertRaisesRegex(SolverEventConflictError, "different payload"):
                    harness.commit_event(
                        "solver-event-conflict",
                        expected_revision=initial["state_revision"],
                        event={"event_id": "event-1", "type": "plan_rejected"},
                        state_updates={"phase": "EXPLORE"},
                    )

                self.assertEqual(committed, harness.get_run("solver-event-conflict"))

    def test_state_updates_cannot_change_run_identity_or_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "showcase.sqlite3"
            with SolverHarness(database_path=database_path) as harness:
                initial = harness.solve("题目", {"run_id": "solver-immutable"})
                for field in ("run_id", "problem_hash", "config_hash", "state_revision"):
                    with self.subTest(field=field):
                        with self.assertRaises(SolverValidationError):
                            harness.commit_event(
                                "solver-immutable",
                                expected_revision=initial["state_revision"],
                                event={"event_id": f"invalid-{field}", "type": "bad_update"},
                                state_updates={field: "forbidden"},
                            )
                self.assertEqual(initial, harness.get_run("solver-immutable"))

    def test_event_payload_is_redacted_before_it_is_returned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "showcase.sqlite3"
            with SolverHarness(database_path=database_path) as harness:
                initial = harness.solve("题目", {"run_id": "solver-redacted-event"})
                result = harness.commit_event(
                    "solver-redacted-event",
                    expected_revision=initial["state_revision"],
                    event={
                        "event_id": "event-redacted",
                        "type": "review_recorded",
                        "token": "SECRET_EVENT_TOKEN",
                        "full_prompt": "SECRET_EVENT_PROMPT",
                    },
                )

                saved_event = result["events"][-1]
                self.assertEqual("[redacted]", saved_event["token"])
                self.assertEqual("[redacted]", saved_event["full_prompt"])
                self.assertNotIn("SECRET_EVENT_TOKEN", repr(result))
                self.assertNotIn("SECRET_EVENT_PROMPT", repr(result))


if __name__ == "__main__":
    unittest.main()
