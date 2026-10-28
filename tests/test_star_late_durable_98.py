"""Durable late-usage evidence under a real SQLite writer lock (#98)."""
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from showcase import run_budget_late
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits


class LateDurableEvidenceTests(unittest.TestCase):
    def setUp(self):
        network = patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden"))
        network.start()
        self.addCleanup(network.stop)

    @contextmanager
    def locked_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ledger = RunBudgetLedger(database_path=root / "budget.sqlite")
            ledger.connection.execute("PRAGMA busy_timeout = 10")
            call = ledger.ensure("run", RunBudgetLimits()).model_call("explore", deadline_at=time.time() + 60)
            event = {"attempt_id": "attempt", "max_tokens": 32, "deadline_at": call.deadline_at}
            call.before_attempt(event, input_estimate=8)
            call.after_attempt({**event, "status": "unknown", "error_category": "timeout"})
            locker = sqlite3.connect(ledger.database_path)
            locker.execute("BEGIN IMMEDIATE")
            try:
                yield root, ledger, call, event, locker
            finally:
                locker.rollback()
                locker.close()
                ledger.close()

    def test_default_sidecar_preserves_unknown_usage_then_completes_idempotently(self):
        with self.locked_attempt() as (root, ledger, call, event, locker):
            records = []
            for observation in (
                {"status": "unknown", "prompt_tokens": 7, "error_category": "missing_finish_reason"},
                {"status": "success", "prompt_tokens": 99, "completion_tokens": 3, "total_tokens": 102},
                {"status": "success", "prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10,
                 "completion_tokens_details": {"reasoning_tokens": 2},
                 "prompt_tokens_details": {"cached_tokens": 4}},
            ):
                before = set(root.rglob("*.json"))
                with self.assertLogs("showcase.run_budget_late", level="WARNING"):
                    run_budget_late.settle_late_with_retry(call, {**event, **observation})
                record, = set(root.rglob("*.json")) - before
                records.append(record)
            self.assertEqual(root / "budget.sqlite.late-usage" / "pending", records[0].parent)
            locker.rollback()
            self.assertTrue(run_budget_late.reconcile_late_evidence(ledger, records[0]))
            partial, = ledger.attempts("run")
            self.assertEqual("unknown", partial["status"])
            self.assertEqual(event["deadline_at"], partial["deadline_at"])
            self.assertEqual(40, ledger.snapshot("run")["reserved_tokens"])
            self.assertFalse(run_budget_late.reconcile_late_evidence(ledger, records[1]))
            self.assertEqual(partial, ledger.attempts("run")[0])
            self.assertTrue(run_budget_late.reconcile_late_evidence(ledger, records[2]))
            complete, = ledger.attempts("run")
            self.assertEqual(2, complete["usage"]["reasoning_tokens"])
            self.assertEqual(4, complete["usage"]["cached_tokens"])
            self.assertEqual(10, ledger.snapshot("run")["charged_tokens"])
            self.assertFalse(run_budget_late.reconcile_late_evidence(ledger, records[2]))
            self.assertEqual(1, ledger.snapshot("run")["http_attempts"])

    def test_explicit_unwritable_destination_does_not_fallback_or_claim_saved(self):
        with self.locked_attempt() as (root, ledger, call, event, _locker):
            destination = root / "not-a-directory"
            destination.write_text("occupied", encoding="utf-8")
            ledger.late_usage_evidence_dir = destination
            with self.assertLogs("showcase.run_budget_late", level="WARNING") as messages:
                run_budget_late.settle_late_with_retry(call, {**event, "status": "success", "total_tokens": 10})
            self.assertIn("evidence write failed", " ".join(messages.output))
            self.assertNotIn("evidence saved", " ".join(messages.output))
            self.assertEqual([], list(root.rglob("*.json")))
            self.assertFalse(Path(ledger.database_path + ".late-usage").exists())
            self.assertEqual("occupied", destination.read_text())
            self.assertEqual(40, ledger.snapshot("run")["reserved_tokens"])

    def test_timeout_returns_before_real_sqlite_lock_is_released(self):
        with self.locked_attempt() as (root, ledger, call, event, locker):
            started = time.monotonic()
            run_budget_late.settle_timeout_nonblocking(
                call, {**event, "status": "unknown", "error_category": "timeout"})
            self.assertLess(time.monotonic() - started, .2)
            until = time.monotonic() + 5
            while not list(root.rglob("*.json")) and time.monotonic() < until:
                time.sleep(.01)
            record, = root.rglob("*.json")
            self.assertEqual(40, ledger.snapshot("run")["reserved_tokens"])
            locker.rollback()
            run_budget_late.reconcile_late_evidence(ledger, record)
            self.assertEqual("unknown", ledger.attempts("run")[0]["status"])
            self.assertEqual(event["deadline_at"], ledger.attempts("run")[0]["deadline_at"])
            self.assertEqual(40, ledger.snapshot("run")["reserved_tokens"])

    def test_memory_without_evidence_directory_reports_unavailable(self):
        ledger = RunBudgetLedger()
        call = ledger.ensure("memory", RunBudgetLimits()).model_call("explore")
        ledger.close()
        with self.assertLogs("showcase.run_budget_late", level="WARNING") as messages:
            run_budget_late.settle_late_with_retry(call, {"attempt_id": "a", "status": "success"})
        self.assertIn("evidence unavailable", " ".join(messages.output))

    def test_foreign_database_and_missing_original_attempt_cannot_be_created(self):
        with self.locked_attempt() as (root, ledger, call, event, locker):
            with self.assertLogs("showcase.run_budget_late", level="WARNING"):
                run_budget_late.settle_late_with_retry(call, {**event, "status": "success", "total_tokens": 10})
            record, = root.rglob("*.json")
            foreign = RunBudgetLedger(database_path=root / "other.sqlite")
            try:
                with self.assertRaises(ValueError):
                    run_budget_late.reconcile_late_evidence(foreign, record)
                self.assertIsNone(foreign.snapshot("run"))
            finally:
                foreign.close()
            locker.rollback()
            content = json.loads(record.read_text())
            for key in ("attempt_id", "run_id"):
                invalid = {**content, key: "nonexistent"}
                record.write_text(json.dumps(invalid), encoding="utf-8")
                with self.assertRaises(ValueError):
                    run_budget_late.reconcile_late_evidence(ledger, record)
            self.assertEqual(1, ledger.snapshot("run")["http_attempts"])
            self.assertEqual(40, ledger.snapshot("run")["reserved_tokens"])
            self.assertIsNone(ledger.snapshot("nonexistent"))

    def test_malformed_evidence_is_rejected_without_changing_budget(self):
        with self.locked_attempt() as (root, ledger, call, event, locker):
            with self.assertLogs("showcase.run_budget_late", level="WARNING"):
                run_budget_late.settle_late_with_retry(call, {**event, "status": "success", "total_tokens": 10})
            record, = root.rglob("*.json")
            content = json.loads(record.read_text())
            locker.rollback()
            before = ledger.attempts("run")
            for invalid in ([], {**content, "usage": []}, {**content, "error_category": "private-prompt"}):
                record.write_text(json.dumps(invalid), encoding="utf-8")
                with self.assertRaises(ValueError):
                    run_budget_late.reconcile_late_evidence(ledger, record)
                self.assertEqual(before, ledger.attempts("run"))

    def test_failed_file_sync_is_not_reported_as_durable_evidence(self):
        with self.locked_attempt() as (root, ledger, call, event, _locker):
            with patch("showcase.run_budget_late.os.fsync", side_effect=OSError("private-error")):
                with self.assertLogs("showcase.run_budget_late", level="WARNING") as messages:
                    run_budget_late.settle_late_with_retry(call, {**event, "status": "success", "total_tokens": 10})
            self.assertIn("evidence write failed", " ".join(messages.output))
            self.assertNotIn("private-error", " ".join(messages.output))
            self.assertEqual([], list(root.rglob("*.json")))
            self.assertEqual([], list(root.rglob("*.tmp")))
            self.assertEqual(40, ledger.snapshot("run")["reserved_tokens"])

    def test_closed_memory_evidence_does_not_promise_recoverable_settlement(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = RunBudgetLedger()
            ledger.late_usage_evidence_dir = Path(folder)
            call = ledger.ensure("memory", RunBudgetLimits()).model_call("explore")
            event = {"attempt_id": "memory-attempt", "max_tokens": 32}
            call.before_attempt(event, input_estimate=8)
            ledger.close()
            with self.assertLogs("showcase.run_budget_late", level="WARNING") as messages:
                run_budget_late.settle_late_with_retry(call, {**event, "status": "success", "total_tokens": 10})
            self.assertIn("in-memory ledger cannot be recovered", " ".join(messages.output))
            record, = Path(folder).rglob("*.json")
            self.assertIsNone(json.loads(record.read_text())["database_id"])
            replacement = RunBudgetLedger()
            try:
                with self.assertRaises(ValueError):
                    run_budget_late.reconcile_late_evidence(replacement, record)
                self.assertIsNone(replacement.snapshot("memory"))
            finally:
                replacement.close()

    def test_locked_late_usage_can_be_reconciled_after_restart_without_redispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            database = root / "budget.sqlite"
            evidence_dir = root / "explicit-evidence"
            deadline = time.time() + 60
            ledger = RunBudgetLedger(database_path=database)
            ledger.late_usage_evidence_dir = evidence_dir
            ledger.connection.execute("PRAGMA busy_timeout = 20")
            ledger.connection.execute(
                "CREATE TABLE terminal_marker (final_text TEXT, arm TEXT, status TEXT)"
            )
            ledger.connection.execute(
                "INSERT INTO terminal_marker VALUES ('unchanged', 'arm-2', 'failed')"
            )
            ledger.connection.commit()
            budget = ledger.ensure("run-late-98", RunBudgetLimits(max_runtime_seconds=60))
            call = budget.model_call("explore", deadline_at=deadline)
            attempt = {
                "attempt_id": "original-attempt-98",
                "max_tokens": 32,
                "deadline_at": deadline,
            }
            call.before_attempt(attempt, input_estimate=8)
            call.after_attempt({**attempt, "status": "unknown", "error_category": "timeout"})
            before_attempt, = ledger.attempts(budget.run_id)
            before = ledger.snapshot(budget.run_id)
            self.assertEqual(1, before["unresolved_attempts"])
            self.assertEqual(40, before["reserved_tokens"])
            self.assertEqual(deadline, before_attempt["deadline_at"])
            event = {
                **attempt,
                "status": "success",
                "http_status": 200,
                "prompt_tokens": 7,
                "completion_tokens": 3,
                "total_tokens": 10,
                "prompt": "private-prompt-must-not-be-written",
                "response": "private-answer-must-not-be-written",
                "authorization": "private-token-must-not-be-written",
            }
            locker = sqlite3.connect(str(database), timeout=0.1)
            locker.execute("BEGIN IMMEDIATE")
            try:
                # Keep a real database writer lock through all finite retries.
                with patch.object(socket.socket, "connect", side_effect=AssertionError("network")):
                    with self.assertLogs("showcase.run_budget_late", level="WARNING"):
                        run_budget_late.settle_late_with_retry(call, event)
                pending, = ledger.attempts(budget.run_id)
                self.assertEqual("original-attempt-98", pending["attempt_id"])
                self.assertEqual("unknown", pending["status"])
                self.assertEqual(40, ledger.snapshot(budget.run_id)["reserved_tokens"])
                records = list(evidence_dir.rglob("*.json"))
                self.assertEqual(1, len(records), "late usage was not durably saved")
                evidence = records[0].read_text(encoding="utf-8")
                self.assertNotIn("private-prompt", evidence)
                self.assertNotIn("private-answer", evidence)
                self.assertNotIn("private-token", evidence)
                record = json.loads(evidence)
                self.assertEqual("run-late-98", record["run_id"])
                self.assertEqual("original-attempt-98", record["attempt_id"])
                self.assertEqual(10, record["usage"]["total_tokens"])
                self.assertNotEqual("settled", record.get("settlement_status"))
            finally:
                locker.rollback()
                locker.close()
                ledger.close()

            # Each invocation is a fresh interpreter and reopens the same original DB.
            script = r'''
import json, socket, sqlite3, sys
from unittest.mock import patch
from showcase.run_budget import RunBudgetLedger
from showcase.run_budget_late import reconcile_late_evidence
with patch.object(socket.socket, "connect", side_effect=AssertionError("network")):
    ledger = RunBudgetLedger(database_path=sys.argv[1])
    try:
        reconcile_late_evidence(ledger, sys.argv[2])
        row = ledger.connection.execute("SELECT final_text, arm, status FROM terminal_marker").fetchone()
        print(json.dumps({"attempts": ledger.attempts("run-late-98"),
                          "budget": ledger.snapshot("run-late-98"), "marker": row}))
    finally:
        ledger.close()
'''
            recovered = []
            for _ in range(2):
                result = subprocess.run(
                    [sys.executable, "-c", script, str(database), str(records[0])],
                    capture_output=True, text=True, check=False, env=os.environ.copy(), timeout=15,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                recovered.append(json.loads(result.stdout))
            for result in recovered:
                settled, = result["attempts"]
                self.assertEqual("original-attempt-98", settled["attempt_id"])
                self.assertEqual(deadline, settled["deadline_at"])
                self.assertEqual("success", settled["status"])
                self.assertEqual(10, settled["usage"]["total_tokens"])
                self.assertEqual(1, result["budget"]["http_attempts"])
                self.assertEqual(0, result["budget"]["unresolved_attempts"])
                self.assertEqual(0, result["budget"]["reserved_tokens"])
                self.assertEqual(10, result["budget"]["charged_tokens"])
                self.assertEqual(["unchanged", "arm-2", "failed"], result["marker"])
            self.assertEqual(recovered[0]["attempts"], recovered[1]["attempts"])


if __name__ == "__main__":
    unittest.main()
