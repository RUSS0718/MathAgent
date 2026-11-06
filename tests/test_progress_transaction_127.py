"""A failed progress event must not poison the shared Job/budget transaction."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from showcase.run_budget import RunBudgetLedger, RunBudgetLimits
from showcase.storage import SQLiteStore
from showcase.workspace import WorkspaceStore


class ProgressTransactionTest(unittest.TestCase):
    def test_failed_progress_rolls_back_and_budget_can_settle(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        with SQLiteStore(Path(temporary.name) / "workspace.sqlite") as base:
            store = WorkspaceStore(base.database_path, connection=base._connection)
            ledger = RunBudgetLedger(store._connection, connection_lock=store._lock)
            session = store.create_session("owner")
            job, _ = store.create_job(
                user_id="owner", session_id=session, problem="1+1",
                idempotency_key="progress-failure", request_digest="digest",
                execution_mode="star_limited", solver_identity={"solver_mode": "star_limited"},
            )
            run_id = job["job_id"]
            ledger.ensure(run_id, RunBudgetLimits())
            store.start_job(run_id, execution_mode="star_limited")
            action_id, _ = ledger.reserve(run_id, "http", output_cap=100)
            progress = {"type": "solver_progress", "solver_event_id": "solver_event_test",
                        "solver": {"state_revision": 1}}
            with patch.object(store, "_insert_event", side_effect=sqlite3.OperationalError("database is locked")):
                with self.assertRaisesRegex(sqlite3.OperationalError, "database is locked"):
                    store.append_event(run_id, progress)
            self.assertNotIn("solver", store.get_job(run_id, "owner")["result"])
            ledger.settle(run_id, action_id, {"status": "unknown"})
            self.assertEqual(1, ledger.snapshot(run_id)["unresolved_attempts"])
            store.append_event(run_id, progress)
            self.assertEqual(1, store.get_job(run_id, "owner")["result"]["solver"]["state_revision"])

    def test_reader_contention_does_not_leave_a_nested_transaction(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        with SQLiteStore(Path(temporary.name) / "workspace.sqlite") as base:
            store = WorkspaceStore(base.database_path, connection=base._connection)
            session = store.create_session("owner")
            job, _ = store.create_job(
                user_id="owner", session_id=session, problem="1+1",
                idempotency_key="read-contention", request_digest="digest",
                execution_mode="star_limited", solver_identity={"solver_mode": "star_limited"},
            )
            store.start_job(job["job_id"], execution_mode="star_limited")
            reader = sqlite3.connect(base.database_path)
            try:
                reader.execute("BEGIN")
                reader.execute("SELECT * FROM workspace_jobs").fetchall()
                base._connection.execute("PRAGMA busy_timeout=10")
                event = {"type": "solver_progress", "solver_event_id": "reader-contention",
                         "solver": {"state_revision": 1}}
                with self.assertRaisesRegex(sqlite3.OperationalError, "database is locked"):
                    store.append_event(job["job_id"], event)
                reader.rollback()
                store.append_event(job["job_id"], event)
                self.assertEqual(1, store.get_job(job["job_id"], "owner")["result"]["solver"]["state_revision"])
            finally:
                reader.close()


if __name__ == "__main__":
    unittest.main()
