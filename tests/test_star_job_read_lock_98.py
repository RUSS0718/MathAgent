"""Public Job reads while a database writer occupies the workspace gate."""

import contextlib
import sqlite3
import threading
import time
import unittest
from unittest.mock import patch

import requests

from showcase.star_experiment_policy import ExperimentRunPolicy
from showcase.workspace import WorkspaceError
from tests.star_product_support import StarJobFixture


class JobReadLockTest(StarJobFixture, unittest.TestCase):
    def test_job_read_at_deadline_does_not_wait_for_blocked_workspace_writer(self):
        deadline = time.time() + 2
        self.open_star([], SHOWCASE_STAR_EXPERIMENT_POLICY=ExperimentRunPolicy(
            time.time() + 20, phase_deadline_at=deadline),
            SHOWCASE_STAR_FEATURES={"strict_completion": True})
        service = self.app.extensions["showcase_workspace_service"]
        delivered = threading.Event()
        writer_gate = threading.Event()
        writer_holding = threading.Event()
        workspace_gate = threading.Event()
        finished = threading.Event()
        calls, reads, errors = [], [], []
        self.addCleanup(writer_gate.set)

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

        def transport(_url, **_kwargs):
            calls.append(True)
            yield "headers", Reply()
            delivered.set()
            threading.Event().wait(max(0, deadline - time.time()))
            raise requests.ReadTimeout("offline deadline")

        def external_writer():
            try:
                with contextlib.closing(sqlite3.connect(service.store.database_path)) as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    writer_holding.set()
                    writer_gate.wait(8)
                    connection.rollback()
            except Exception as exc:
                errors.append(exc)

        def blocked_workspace_writer():
            try:
                with service.store._lock:
                    workspace_gate.set()
                    service.store._connection.execute("BEGIN IMMEDIATE")
                    service.store._connection.rollback()
            except Exception as exc:
                errors.append(exc)

        def read_job(job_id):
            try:
                reads.append(self.job(job_id))
            except Exception as exc:
                errors.append(exc)
            finally:
                finished.set()

        with patch("showcase.request_transport.response_events", side_effect=transport):
            job_id = self.create_job()
            self.assertTrue(delivered.wait(3))
            self.assertNotIn("observation", self.job(job_id))
            external = threading.Thread(target=external_writer, daemon=True)
            external.start()
            self.assertTrue(writer_holding.wait(3))
            competing = threading.Thread(target=blocked_workspace_writer, daemon=True)
            competing.start()
            self.assertTrue(workspace_gate.wait(3))
            threading.Event().wait(max(0, deadline - time.time()) + .05)
            reader = threading.Thread(target=read_job, args=(job_id,), daemon=True)
            reader.start()
            try:
                self.assertTrue(finished.wait(1), "Job read waited for a blocked workspace writer")
                self.assertEqual([], errors)
                job, = reads
                self.assertEqual("running", job["status"])
                self.assertEqual("deadline_unconfirmed", job["observation"]["state"])
                self.assertFalse(job["observation"]["terminal_persisted"])
                self.assertEqual(job["result"]["request_attempts"][-1]["attempt_id"],
                                 job["observation"]["attempt_id"])
                self.assertGreater(job["result"]["budget"]["reserved_tokens"], 0)
                self.assertEqual(1, job["result"]["budget"]["unresolved_attempts"])
                self.assertEqual([True], calls)
                self.assertFalse(writer_gate.is_set())
                with self.assertRaises(WorkspaceError) as denied:
                    service.get_job(job_id, "another-user")
                self.assertEqual(404, denied.exception.status)
            finally:
                writer_gate.set()
                external.join(4)
                competing.join(4)
                reader.join(4)
            terminal = self.terminal(job_id)
            self.assertEqual("failed", terminal["status"])
            self.assertNotIn("observation", terminal)
            self.assertEqual([True], calls)
