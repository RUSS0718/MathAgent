"""Explicitly abandoning interrupted work keeps unknown costs and restores capacity."""

import json
import os
import threading
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from tests import test_faithful_s10_intervention_execution as support


class PairRecoveryTest(unittest.TestCase):
    setUp = support.InterventionExecutionTest.setUp
    reserve = support.InterventionExecutionTest.reserve

    def test_explicit_abandon_releases_only_unused_holds_without_redispatch(self):
        from showcase.solver_harness.faithful_intervention_execution import abandon_interrupted_pair

        self.reserve(reservation={"input_estimate": 10, "output_cap": 20,
                                  "tool_calls": 2, "time_seconds": 20})

        def crash(*, budget, branch_id, **_):
            call = budget.model_call("reasoner")
            call.before_attempt({"attempt_id": branch_id + ":http", "max_tokens": 20}, input_estimate=10)
            raise KeyboardInterrupt()

        with self.assertRaises(KeyboardInterrupt):
            self.engine.execute_pair("pair-1", execute_branch=crash,
                                     ledger=self.ledger, job_gate=self.gate)
        row = self.connection.execute(
            "SELECT report_json FROM faithful_intervention_pairs WHERE pair_id='pair-1'"
        ).fetchone()
        report = json.loads(row[0])
        report["arms"]["control"]["started_at_utc"] = (
            datetime.now(UTC) - timedelta(seconds=2)
        ).isoformat()
        self.connection.execute(
            "UPDATE faithful_intervention_pairs SET report_json=? WHERE pair_id='pair-1'",
            (json.dumps(report),),
        )
        self.connection.commit()
        report = abandon_interrupted_pair(self.engine, "pair-1", ledger=self.ledger, job_gate=self.gate)
        self.assertEqual("interrupted", report["status"])
        self.assertEqual(1, report["denominator"])
        self.assertEqual(1, report["unknown_pairs"])
        budget = self.ledger.snapshot("parent-run")
        self.assertEqual(1, budget["http_attempts"])
        self.assertEqual(30, budget["reserved_tokens"])
        self.assertEqual(1, budget["unknown_attempts"])
        stored_ledger = json.loads(self.connection.execute(
            "SELECT ledger_json FROM run_budgets WHERE run_id='parent-run'"
        ).fetchone()[0])
        self.assertEqual({"control": 20}, stored_ledger["intervention_time_holds"]["pair-1"])
        resources = budget["intervention_resources"]["pair-1"]
        self.assertGreaterEqual(resources["arm_wall_time_seconds"], 1.5)
        self.assertGreaterEqual(resources["arm_elapsed_at_recovery_seconds"], 1.5)
        self.assertEqual(report, abandon_interrupted_pair(
            self.engine, "pair-1", ledger=self.ledger, job_gate=self.gate))
        self.assertEqual(report, self.engine.execute_pair(
            "pair-1", execute_branch=lambda **_: self.fail("redispatch"),
            ledger=self.ledger, job_gate=self.gate))

    def test_reserved_pair_cannot_be_abandoned_before_dispatch(self):
        from showcase.solver_harness.faithful_intervention_execution import abandon_interrupted_pair
        from showcase.solver_harness.faithful_intervention_records import FaithfulInterventionError

        self.reserve()
        with self.assertRaises(FaithfulInterventionError):
            abandon_interrupted_pair(self.engine, "pair-1", ledger=self.ledger, job_gate=self.gate)

    def test_live_owner_in_another_process_cannot_be_abandoned(self):
        from showcase.faithful_intervention_control import (
            authorize_explicit_resume,
            ensure_control_schema,
        )
        from showcase.workspace import WorkspaceError

        self.reserve()
        self.connection.execute(
            "CREATE TABLE faithful_intervention_pair_owners (pair_id TEXT PRIMARY KEY,job_id TEXT,"
            "owner_pid INTEGER,owner_started REAL,execution_status TEXT,updated_at REAL)"
        )
        self.connection.execute(
            "INSERT INTO faithful_intervention_pair_owners VALUES ('pair-1','job-1',999999,NULL,'running',0)"
        )
        report = json.loads(self.connection.execute(
            "SELECT report_json FROM faithful_intervention_pairs WHERE pair_id='pair-1'"
        ).fetchone()[0])
        report.update(status="running", started_pairs=1, denominator=1)
        report["arms"]["control"]["status"] = "dispatching"
        self.connection.execute(
            "UPDATE faithful_intervention_pairs SET report_json=? WHERE pair_id='pair-1'",
            (json.dumps(report),),
        )
        ensure_control_schema(self.connection)
        self.connection.execute(
            "INSERT INTO faithful_intervention_control(job_id,run_id,status,updated_at) "
            "VALUES ('job-1','parent-run','paused',0)"
        )
        self.connection.commit()
        with patch("showcase.faithful_intervention_control.os.kill", side_effect=PermissionError):
            with self.assertRaisesRegex(WorkspaceError, "intervention_pair_execution_active"):
                authorize_explicit_resume(self.connection, "job-1")
        self.assertEqual(60, self.ledger.snapshot("parent-run")["reserved_tokens"])
        persisted = json.loads(self.connection.execute(
            "SELECT report_json FROM faithful_intervention_pairs WHERE pair_id='pair-1'"
        ).fetchone()[0])
        self.assertEqual("running", persisted["status"])

    def test_live_executor_cannot_be_abandoned_by_concurrent_control(self):
        from showcase.solver_harness.faithful_intervention_execution import abandon_interrupted_pair
        from showcase.solver_harness.faithful_intervention_records import (
            BranchOutcome,
            FaithfulInterventionError,
        )

        self.reserve()

        def execute(**_):
            with self.assertRaises(FaithfulInterventionError):
                abandon_interrupted_pair(self.engine, "pair-1", ledger=self.ledger, job_gate=self.gate)
            return BranchOutcome("unknown_outcome")

        self.engine.execute_pair("pair-1", execute_branch=execute,
                                 ledger=self.ledger, job_gate=self.gate)

    def test_scheduled_but_not_started_owner_blocks_explicit_parent_resume(self):
        from showcase.faithful_intervention_control import (
            authorize_explicit_resume,
            ensure_control_schema,
            register_worker,
            unregister_worker,
        )
        from showcase.workspace import WorkspaceError

        self.reserve()
        ensure_control_schema(self.connection)
        self.connection.execute(
            "INSERT INTO faithful_intervention_control(job_id,run_id,status,updated_at) "
            "VALUES ('job-1','parent-run','paused',0)"
        )
        self.connection.execute(
            "INSERT INTO faithful_intervention_pair_owners "
            "(pair_id,job_id,owner_pid,owner_started,execution_status,updated_at) "
            "VALUES ('pair-1','job-1',?,0,'scheduled',0)", (os.getpid(),)
        )
        report = json.loads(self.connection.execute(
            "SELECT report_json FROM faithful_intervention_pairs WHERE pair_id='pair-1'"
        ).fetchone()[0])
        report.update(status="running", started_pairs=1, denominator=1)
        self.connection.execute(
            "UPDATE faithful_intervention_pairs SET report_json=? WHERE pair_id='pair-1'",
            (json.dumps(report),),
        )
        self.connection.commit()
        worker = threading.Thread(target=lambda: None)
        register_worker("pair-1", worker)
        try:
            with self.assertRaisesRegex(WorkspaceError, "intervention_pair_execution_active"):
                authorize_explicit_resume(self.connection, "job-1")
        finally:
            unregister_worker("pair-1")
        self.assertEqual(60, self.ledger.snapshot("parent-run")["reserved_tokens"])
        persisted = json.loads(self.connection.execute(
            "SELECT report_json FROM faithful_intervention_pairs WHERE pair_id='pair-1'"
        ).fetchone()[0])
        self.assertEqual("running", persisted["status"])

    def test_dead_owner_resume_persists_unknown_denominator_and_keeps_unsettled_holds(self):
        from showcase.faithful_intervention_control import (
            authorize_explicit_resume,
            ensure_control_schema,
        )

        self.reserve(reservation={"input_estimate": 10, "output_cap": 20,
                                  "tool_calls": 2, "time_seconds": 20})
        from showcase.solver_harness.faithful_intervention_execution import ArmBudget

        call = ArmBudget(
            self.ledger, "parent-run", "faithful_intervention:pair-1:control"
        ).model_call("reasoner", solver_call_id="dead-owner-call")
        call.before_attempt(
            {"attempt_id": "dead-owner-attempt", "max_tokens": 20}, input_estimate=10
        )
        report = json.loads(self.connection.execute(
            "SELECT report_json FROM faithful_intervention_pairs WHERE pair_id='pair-1'"
        ).fetchone()[0])
        report.update(status="running", started_pairs=1, denominator=1)
        report["arms"]["control"].update(status="dispatching", started_at_utc=datetime.now(UTC).isoformat())
        self.connection.execute(
            "UPDATE faithful_intervention_pairs SET report_json=? WHERE pair_id='pair-1'",
            (json.dumps(report),),
        )
        ensure_control_schema(self.connection)
        self.connection.execute(
            "INSERT INTO faithful_intervention_control(job_id,run_id,status,updated_at) "
            "VALUES ('job-1','parent-run','paused',0)"
        )
        self.connection.execute(
            "INSERT INTO faithful_intervention_pair_owners "
            "(pair_id,job_id,owner_pid,owner_started,execution_status,updated_at) "
            "VALUES ('pair-1','job-1',999999,0,'running',0)"
        )
        self.connection.commit()

        with patch("showcase.faithful_intervention_control.os.kill", side_effect=ProcessLookupError):
            authorize_explicit_resume(self.connection, "job-1")

        persisted = self.engine.get_pair("pair-1")
        self.assertEqual("interrupted", persisted["status"])
        self.assertEqual(1, persisted["denominator"])
        self.assertEqual(1, persisted["unknown_pairs"])
        self.assertIsNone(persisted["effect"])
        ledger = json.loads(self.connection.execute(
            "SELECT ledger_json FROM run_budgets WHERE run_id='parent-run'"
        ).fetchone()[0])
        self.assertEqual({"control": 20}, ledger["intervention_time_holds"]["pair-1"])
        self.assertEqual(1, self.ledger.snapshot("parent-run")["unknown_attempts"])
        self.assertEqual("resuming", self.connection.execute(
            "SELECT status FROM faithful_intervention_control WHERE job_id='job-1'"
        ).fetchone()[0])


if __name__ == "__main__":
    unittest.main()
