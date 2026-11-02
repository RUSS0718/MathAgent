"""Shared Workspace and budget transaction regressions."""

from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from showcase.flask_app import create_app


class StarWorkspaceTransactionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "showcase-v0.2"
        self.app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": str(self.root)})

    def tearDown(self) -> None:
        self.app.extensions["showcase_workspace_service"].close()
        self.app.extensions["showcase_run_service"].close()
        self.app.extensions["loopback_store"].close()
        self.temp_dir.cleanup()

    def test_star_service_uses_workspace_connection_for_budget_writes(self) -> None:
        from showcase.workspace import WorkspaceService

        with tempfile.TemporaryDirectory() as directory:
            service = WorkspaceService(
                Path(directory) / "star.sqlite",
                star_pipeline=SimpleNamespace(checkpointer=None),
                worker_enabled=False,
            )
            try:
                self.assertIs(service.budget_ledger.connection, service.store._connection)
                self.assertIs(service.budget_ledger.connection_lock, service.store._lock)
                self.assertIsNot(service.budget_ledger.lock, service.store._lock)
            finally:
                service.close()

    def test_star_terminal_transaction_rolls_back_job_snapshot_and_budget(self) -> None:
        from showcase.run_budget import RunBudgetLimits

        service = self.app.extensions["showcase_workspace_service"]
        session_id = service.create_session("user-1")
        payload, existing = service.store.create_job(
            user_id="user-1",
            session_id=session_id,
            problem="1+1",
            idempotency_key=str(uuid.uuid4()),
            request_digest="digest",
            execution_mode="star_limited",
            solver_identity={"solver_mode": "star_limited"},
        )
        self.assertFalse(existing)
        job_id = payload["job_id"]
        service.budget_ledger.ensure(
            job_id, RunBudgetLimits(max_model_calls=2, max_http_attempts=2, max_tool_calls=0)
        )
        self.assertTrue(service.store.start_job(job_id, execution_mode="star_limited"))
        before_snapshot = service.store._connection.execute(
            "SELECT snapshot_json FROM runs WHERE run_id=?", (job_id,)
        ).fetchone()[0]

        with patch.object(service.store, "_insert_event", side_effect=RuntimeError("event write")):
            with self.assertRaisesRegex(RuntimeError, "event write"):
                service.store.complete_job(job_id, "answer", "summary")

        row = service.store._connection.execute(
            "SELECT status,result_json FROM workspace_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        snapshot = service.store._connection.execute(
            "SELECT snapshot_json FROM runs WHERE run_id=?", (job_id,)
        ).fetchone()[0]
        budget = service.budget_ledger.snapshot(job_id)
        self.assertEqual("running", row[0])
        self.assertEqual("star_limited", json.loads(row[1])["execution_mode"])
        self.assertEqual(before_snapshot, snapshot)
        self.assertIsNone(budget["ended_at"])


if __name__ == "__main__":
    unittest.main()
