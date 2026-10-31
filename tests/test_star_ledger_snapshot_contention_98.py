"""Transient SQLite commit contention must not break public ledger reads."""

import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from showcase.run_budget import RunBudgetLedger, RunBudgetLimits


class LedgerSnapshotContentionTest(unittest.TestCase):
    def test_reader_tolerates_a_brief_writer_commit_while_ledger_gate_is_held(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "budget.sqlite"
            ledger = RunBudgetLedger(database_path=path)
            budget = ledger.ensure("snapshot-contention", RunBudgetLimits(max_runtime_seconds=10))
            writer = sqlite3.connect(path, check_same_thread=False)
            held, release, executing, done = (threading.Event() for _ in range(4))
            failures, results = [], []

            def hold_gate():
                with ledger.lock:
                    held.set()
                    release.wait(5)

            def read():
                try:
                    results.append(ledger.view(budget.run_id))
                except BaseException as exc:
                    failures.append(exc)
                finally:
                    done.set()

            actual_connect = sqlite3.connect

            class ObservedConnection:
                def __init__(self, connection):
                    self.connection = connection

                def execute(self, sql, parameters):
                    executing.set()
                    return self.connection.execute(sql, parameters)

                def close(self):
                    self.connection.close()

            def open_reader(*args, **kwargs):
                return ObservedConnection(actual_connect(*args, **kwargs))

            try:
                threading.Thread(target=hold_gate, daemon=True).start()
                self.assertTrue(held.wait(3))
                writer.execute("BEGIN EXCLUSIVE")
                with patch("showcase.run_budget.sqlite3.connect", side_effect=open_reader):
                    worker = threading.Thread(target=read, daemon=True)
                    worker.start()
                    self.assertTrue(executing.wait(3))
                    self.assertFalse(done.wait(.05), "transient SQLite writer caused immediate read failure")
                    writer.commit()
                    self.assertTrue(done.wait(3))
                    worker.join(1)
                self.assertEqual([], failures)
                self.assertEqual(1, len(results))
                self.assertEqual(0, results[0][0]["http_attempts"])
            finally:
                writer.rollback()
                writer.close()
                release.set()
                ledger.close()


if __name__ == "__main__":
    unittest.main()
