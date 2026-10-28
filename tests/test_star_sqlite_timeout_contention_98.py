"""SQLite writer contention must not make a timed-out model call wait."""

import os
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from llm_client import InternChatClient
from showcase.adapters import AdapterError, InternModelAdapter, InternStreamAdapter
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget


class SqliteTimeoutContentionTest(unittest.TestCase):
    def test_timeout_does_not_wait_for_external_writer(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                self.check_timeout_under_writer(streaming)

    def check_timeout_under_writer(self, streaming):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "budget.sqlite"
            ledger = RunBudgetLedger(database_path=path)
            observer = RunBudgetLedger(database_path=path)
            writer = sqlite3.connect(path, check_same_thread=False)
            budget = ledger.ensure(f"sqlite-timeout-{streaming}", RunBudgetLimits(max_runtime_seconds=10))
            held, release, writer_done, finished = (threading.Event() for _ in range(4))
            failures, sends = [], []
            deadline = time.time() + 1

            class Reply:
                status_code = 200

                def raise_for_status(self):
                    pass

            def hold_writer():
                try:
                    writer.execute("BEGIN IMMEDIATE")
                    held.set()
                    release.wait(8)
                    writer.rollback()
                finally:
                    writer_done.set()

            def transport(_url, **_kwargs):
                sends.append(True)
                yield "headers", Reply()
                threading.Thread(target=hold_writer, daemon=True).start()
                if not held.wait(3):
                    raise AssertionError("SQLite writer not held")
                threading.Event().wait(max(0, deadline - time.time()))
                raise requests.ReadTimeout("offline timeout")

            with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
                adapter = (InternStreamAdapter if streaming else InternModelAdapter)(
                    InternChatClient(timeout=5, retry=3), max_tokens=32)

            def call():
                try:
                    with bind_budget(budget):
                        operation = adapter.stream_complete if streaming else adapter.complete
                        result = operation([{"role": "user", "content": "offline"}], metadata={
                            "role": "explore", "strict_completion": True, "phase_deadline_at": deadline})
                        if streaming:
                            list(result)
                except BaseException as exc:
                    failures.append(exc)
                finally:
                    finished.set()

            try:
                with patch("showcase.request_transport.response_events", side_effect=transport):
                    worker = threading.Thread(target=call, daemon=True)
                    worker.start()
                    self.assertTrue(held.wait(4))
                    returned_under_lock = finished.wait(max(0, deadline - time.time()) + 1.5)
                    pending, = observer.attempts(budget.run_id)
                    before = observer.snapshot(budget.run_id)
                    release.set()
                    self.assertTrue(writer_done.wait(3))
                    self.assertTrue(finished.wait(4))
                    worker.join(1)
                    self.assertTrue(returned_under_lock, "timeout waited for SQLite writer")
                    self.assertEqual(1, len(failures))
                    self.assertIsInstance(failures[0], AdapterError)
                    self.assertEqual("timeout", failures[0].category)
                    self.assertEqual([True], sends)
                    self.assertNotEqual("not_submitted", pending["dispatch_status"])
                    self.assertGreater(before["reserved_tokens"], 0)
                    self.assertEqual(1, before["unresolved_attempts"])
                    until = time.monotonic() + 4
                    while time.monotonic() < until:
                        settled, = observer.attempts(budget.run_id)
                        if settled.get("error_category") == "timeout":
                            break
                        time.sleep(.01)
                    self.assertEqual("timeout", settled.get("error_category"))
                    self.assertEqual(pending["attempt_id"], settled["attempt_id"])
                    self.assertEqual(before["reserved_tokens"], observer.snapshot(budget.run_id)["reserved_tokens"])
                    with ledger.lock:
                        self.assertEqual(5000, ledger.connection.execute("PRAGMA busy_timeout").fetchone()[0])
            finally:
                release.set()
                writer.close()
                observer.close()
                ledger.close()


if __name__ == "__main__":
    unittest.main()
