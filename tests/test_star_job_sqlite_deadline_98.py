"""Public Job observation while the persisted ledger owns a SQLite write lock."""

import contextlib
import json
import sqlite3
import threading
import time
import unittest
from unittest.mock import patch

import requests

from showcase.star_experiment_policy import ExperimentRunPolicy
from tests.star_product_support import SOLVED, StarJobFixture


class JobSqliteDeadlineTest(StarJobFixture, unittest.TestCase):
    def test_write_lock_keeps_unknown_attempt_visible_until_terminal_is_persisted(self):
        deadline = time.time() + 2
        self.open_star([], SHOWCASE_STAR_EXPERIMENT_POLICY=ExperimentRunPolicy(
            time.time() + 15, phase_deadline_at=deadline),
            SHOWCASE_STAR_FEATURES={"strict_completion": True})
        service = self.app.extensions["showcase_workspace_service"]
        ledger = service.budget_ledger
        held, release, holder_done, timeout_sent, observed = (threading.Event() for _ in range(5))
        self.addCleanup(release.set)
        sends, callbacks, responses, errors = [], [], [], []

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

        reply = Reply()
        body = json.dumps({"choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps(SOLVED)}}], "usage": {
                "prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}).encode()

        def hold_writer():
            try:
                with ledger.lock:
                    ledger.connection.execute("BEGIN IMMEDIATE")
                    held.set()
                    release.wait(10)
                    ledger.connection.rollback()
            finally:
                holder_done.set()

        def transport(_url, *, on_late_response, **_kwargs):
            sends.append(True)
            callbacks.append(on_late_response)
            yield "headers", reply
            threading.Thread(target=hold_writer, daemon=True).start()
            if not held.wait(3):
                raise AssertionError("SQLite writer was not acquired")
            threading.Event().wait(max(0, deadline - time.time()))
            timeout_sent.set()
            raise requests.ReadTimeout("offline deadline")

        def observe(job_id):
            try:
                responses.append(self.job(job_id))
            except BaseException as exc:
                errors.append(exc)
            finally:
                observed.set()

        try:
            with patch("showcase.request_transport.response_events", side_effect=transport):
                job_id = self.create_job()
                self.assertTrue(held.wait(5))
                self.assertTrue(timeout_sent.wait(max(0, deadline - time.time()) + 3),
                                "transport did not reach its deadline")
                reader = threading.Thread(target=observe, args=(job_id,), daemon=True)
                reader.start()
                returned = observed.wait(2)
                try:
                    self.assertTrue(returned, "public Job read waited for the SQLite writer")
                    self.assertEqual([], errors)
                    before, = responses
                    self.assertEqual("running", before["status"])
                    self.assertEqual("needs_review", before["result"]["solver"]["recovery"]["status"])
                    self.assertGreater(before["result"]["budget"]["reserved_tokens"], 0)
                    self.assertEqual(1, before["result"]["budget"]["unresolved_attempts"])
                    original, = before["result"]["request_attempts"]
                    self.assertEqual("unknown", original["status"])
                    self.assertEqual("unknown", original["metering_status"])
                    self.assertLessEqual(original["deadline_at"], time.time())
                    self.assertNotEqual("not_submitted", original["dispatch_status"])
                    self.assertEqual([True], sends)
                    with contextlib.closing(sqlite3.connect(service.store.database_path)) as reader_db:
                        row = reader_db.execute("SELECT status FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
                    self.assertEqual("running", row[0])
                    self.assertFalse(release.is_set())
                finally:
                    release.set()
                self.assertTrue(holder_done.wait(4))
                self.assertTrue(observed.wait(5))
                reader.join(2)
                after = self.terminal(job_id)
                self.assertEqual("failed", after["status"])
                self.assertEqual(original["attempt_id"], after["result"]["request_attempts"][0]["attempt_id"])
                self.assertEqual([True], sends)
                callbacks[0](reply, body, .01, 2, True)
                settled = self.wait_for(lambda: (job if (job := self.job(job_id))["result"]
                    ["budget"]["unresolved_attempts"] == 0 else None))
                self.assertEqual(after["status"], settled["status"])
                self.assertEqual(after["result"].get("solver"), settled["result"].get("solver"))
                self.assertEqual(original["attempt_id"], settled["result"]["request_attempts"][0]["attempt_id"])
                self.assertEqual(10, settled["result"]["request_attempts"][0]["usage"]["total_tokens"])
                self.assertEqual([True], sends)
        finally:
            release.set()


if __name__ == "__main__":
    unittest.main()
