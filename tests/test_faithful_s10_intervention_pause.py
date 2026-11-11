"""Safe-checkpoint pause persistence for native F4 interventions."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


class FaithfulInterventionPauseTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.connection = sqlite3.connect(Path(self.folder.name) / "pause.sqlite3")
        self.connection.row_factory = sqlite3.Row
        self.addCleanup(self.connection.close)
        self.connection.executescript(
            "CREATE TABLE solver_states (run_id TEXT PRIMARY KEY,state_json TEXT,state_revision INTEGER);"
            "CREATE TABLE workspace_jobs (job_id TEXT PRIMARY KEY,status TEXT,updated_at TEXT);"
            "CREATE TABLE workspace_events (event_id INTEGER PRIMARY KEY,job_id TEXT,event_type TEXT,"
            "payload_json TEXT,created_at TEXT);"
            "CREATE TABLE events (run_id TEXT,sequence INTEGER,event_json TEXT,created_at TEXT,"
            "PRIMARY KEY(run_id,sequence));"
        )
        self.state = {
            "phase": "STEP_EXECUTE",
            "calls": {},
            "route_budget": {"closing_reserve": {
                "model_calls": 2, "http_attempts": 2, "tokens": 100,
                "tool_calls": 0, "time_seconds": 20,
            }},
        }
        self.run = {"run_id": "job-1", "state_revision": 4, "state": self.state}
        self.connection.execute(
            "INSERT INTO solver_states VALUES(?,?,?)",
            ("job-1", json.dumps(self.state, sort_keys=True, separators=(",", ":")), 4),
        )
        self.connection.execute("INSERT INTO workspace_jobs VALUES('job-1','running','now')")
        from showcase.faithful_intervention_control import ensure_control_schema

        ensure_control_schema(self.connection)
        self.connection.execute(
            "INSERT INTO faithful_intervention_control(job_id,run_id,status,updated_at) "
            "VALUES('job-1','job-1','pause_requested',0)"
        )
        self.connection.commit()

    def test_pause_commits_only_at_safe_dispatched_step_and_freezes_runtime_identity(self):
        from showcase.faithful_intervention_control import InterventionPaused, maybe_pause

        applied = {"name": "local-test", "max_output_tokens": 256}
        with self.assertRaises(InterventionPaused):
            maybe_pause(
                self.connection,
                self.run,
                {"type": "step_dispatched"},
                {"features": {"serial_routes": True},
                 "applied_model_config": applied},
                "test problem",
            )

        control = self.connection.execute(
            "SELECT status,checkpoint_revision,applied_config_json,applied_config_fingerprint "
            "FROM faithful_intervention_control WHERE job_id='job-1'"
        ).fetchone()
        self.assertEqual("paused", control["status"])
        self.assertEqual(4, control["checkpoint_revision"])
        self.assertEqual(json.dumps(applied, sort_keys=True, separators=(",", ":")),
                         control["applied_config_json"])
        self.assertTrue(control["applied_config_fingerprint"])
        self.assertEqual("waiting_input", self.connection.execute(
            "SELECT status FROM workspace_jobs WHERE job_id='job-1'"
        ).fetchone()[0])
        self.assertEqual(1, self.connection.execute(
            "SELECT COUNT(*) FROM workspace_events WHERE event_type='intervention_pause_requested'"
        ).fetchone()[0])

    def test_pause_waits_when_a_request_is_in_flight_or_event_is_not_dispatch(self):
        from showcase.faithful_intervention_control import maybe_pause

        self.state["calls"] = {"call-1": {"status": "dispatched"}}
        self.connection.execute(
            "UPDATE solver_states SET state_json=? WHERE run_id='job-1'",
            (json.dumps(self.state, sort_keys=True, separators=(",", ":")),),
        )
        self.connection.commit()
        self.run["state"] = self.state
        config = {"applied_model_config": {"name": "local-test"}}
        self.assertIsNone(maybe_pause(
            self.connection, self.run, {"type": "step_dispatched"}, config, "test problem"
        ))
        self.assertEqual("pause_requested", self.connection.execute(
            "SELECT status FROM faithful_intervention_control WHERE job_id='job-1'"
        ).fetchone()[0])
        self.state["calls"] = {}
        self.assertIsNone(maybe_pause(
            self.connection, self.run, {"type": "step_review_dispatched"}, config, "test problem"
        ))


if __name__ == "__main__":
    unittest.main()
