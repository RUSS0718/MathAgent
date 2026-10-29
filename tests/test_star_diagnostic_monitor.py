import hashlib
import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from showcase.run_budget import RunBudgetLedger
from showcase.star_diagnostic import DiagnosticJob
from showcase.star_diagnostic_monitor import monitor
from showcase.star_diagnostic_registration import freeze
from showcase.star_diagnostic_store import initialize, status
from tests.star_diagnostic_support import plan


class MonitorTest(unittest.TestCase):
    def test_first_read_after_wal_producer_closes_preserves_paths_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = freeze(plan(), root / "registration")
            archive = root / "archive"
            archive.mkdir()
            db = sqlite3.connect(archive / "batch.sqlite3")
            try:
                initialize(db, manifest)
                RunBudgetLedger(connection=db)
                status(db, "completed")
            finally:
                db.close()
            self.assertEqual(["batch.sqlite3"], sorted(p.name for p in archive.iterdir()))
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in archive.iterdir()}
            for _ in range(2):
                result = monitor(archive)
                self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                          for p in archive.iterdir()})
                self.assertIn(result["status"], {"completed", "unavailable"})

    def test_missing_database_is_unavailable_and_creates_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "absent"
            result = monitor(path)
            self.assertEqual("unavailable", result["status"])
            self.assertIsNone(result["charged_tokens"])
            self.assertFalse(path.exists())

    def completed_job(self, root):
        freeze(plan(), root / "registration")
        job = DiagnosticJob(root / "registration", root / "archive", root / "registry.db")
        job.run()
        return job

    def test_monitor_is_read_only_and_does_not_read_private_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = self.completed_job(root)
            self.assertEqual(b"\x01\x01", (job.archive / "batch.sqlite3").read_bytes()[18:20])
            self.assertFalse((job.archive / "batch.sqlite3-wal").exists())
            self.assertFalse((job.archive / "batch.sqlite3-shm").exists())
            (job.archive / "private" / "credential.txt").write_text("sentinel-credential")
            def files():
                return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in root.rglob("*") if p.is_file()}
            before = files()
            result = monitor(job.archive)
            self.assertEqual("completed", result["status"])
            self.assertNotIn("sentinel", json.dumps(result))
            self.assertEqual(before, files())

    def test_monitor_observes_wal_commit_and_missing_ledger_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = self.completed_job(root)
            db = sqlite3.connect(job.archive / "batch.sqlite3")
            try:
                self.assertEqual("wal", db.execute("PRAGMA journal_mode=WAL").fetchone()[0])
                db.execute("UPDATE diagnostic_batch SET status='cancelled',last_event='cancelled'")
                db.commit()
                before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in job.archive.iterdir() if p.is_file()}
                for _ in range(3):
                    self.assertEqual("cancelled", monitor(job.archive)["status"])
                    self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                              for p in job.archive.iterdir() if p.is_file()})
                db.execute("DROP TABLE run_budgets")
                db.commit()
                missing = monitor(job.archive)
                self.assertEqual("unavailable", missing["status"])
                self.assertIsNone(missing["charged_tokens"])
            finally:
                db.close()

    def test_wal_monitor_and_repeated_checkpoint_preserve_paths_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            job = self.completed_job(Path(directory))
            database = job.archive / "batch.sqlite3"
            db = sqlite3.connect(database)
            stop, ready = threading.Event(), threading.Event()
            def checkpoint():
                writer = sqlite3.connect(database)
                try:
                    writer.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
                    ready.set()
                    while not stop.wait(.01):
                        writer.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
                finally:
                    writer.close()
            try:
                db.execute("PRAGMA journal_mode=WAL")
                status(db, "cancelled")
                db.execute("PRAGMA wal_checkpoint(FULL)").fetchone()
                with ThreadPoolExecutor(1) as pool:
                    work = pool.submit(checkpoint)
                    try:
                        self.assertTrue(ready.wait(5))
                        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in job.archive.iterdir() if p.is_file()}
                        for _ in range(3):
                            self.assertEqual("cancelled", monitor(job.archive)["status"])
                            self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                                      for p in job.archive.iterdir() if p.is_file()})
                    finally:
                        stop.set()
                        work.result(timeout=5)
            finally:
                db.close()

    def test_corrupt_database_and_write_lock_are_bounded_and_never_free(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = self.completed_job(root)
            db = sqlite3.connect(job.archive / "batch.sqlite3")
            try:
                db.execute("BEGIN IMMEDIATE")
                self.assertEqual("completed", monitor(job.archive)["status"])
                db.rollback()
            finally:
                db.close()
            (job.archive / "batch.sqlite3").write_bytes(b"corrupt")
            self.assertIsNone(monitor(job.archive)["reserved_tokens"])

    def test_extra_ledger_payload_is_not_exposed(self):
        with tempfile.TemporaryDirectory() as directory:
            job = self.completed_job(Path(directory))
            db = sqlite3.connect(job.archive / "batch.sqlite3")
            try:
                run, raw = db.execute("SELECT run_id,ledger_json FROM run_budgets LIMIT 1").fetchone()
                value = json.loads(raw)
                value["limits"]["private_payload"] = "sentinel-credential"
                db.execute("UPDATE run_budgets SET ledger_json=? WHERE run_id=?", (json.dumps(value), run))
                db.commit()
            finally:
                db.close()
            self.assertNotIn("sentinel-credential", json.dumps(monitor(job.archive)))
