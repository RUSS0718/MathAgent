"""Public Job deadline while its persisted attempt ledger gate is occupied."""

import json
import threading
import time
import unittest
from unittest.mock import patch

import requests

from showcase.star_experiment_policy import ExperimentRunPolicy
from tests.star_product_support import SOLVED, StarJobFixture


class JobLedgerLockDeadlineTest(StarJobFixture, unittest.TestCase):
    def test_job_stops_before_ledger_unlock_and_late_reply_only_settles_attempt(self):
        deadline = time.time() + 4
        policy = ExperimentRunPolicy(time.time() + 15, phase_deadline_at=deadline)
        self.open_star([], SHOWCASE_STAR_EXPERIMENT_POLICY=policy,
                       SHOWCASE_STAR_FEATURES={"strict_completion": True})
        ledger = self.app.extensions["showcase_workspace_service"].budget_ledger
        held, release, observed, late_started, late_done = (threading.Event() for _ in range(5))
        self.addCleanup(release.set)
        observations, errors, callbacks, sends = [], [], [], []

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

        reply = Reply()
        body = json.dumps({"choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps(SOLVED)}}], "usage": {
                "prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}).encode()

        def hold_ledger():
            with ledger.lock:
                held.set()
                release.wait(12)

        def transport(_url, *, on_late_response, **_kwargs):
            sends.append(True)
            callbacks.append(on_late_response)
            yield "headers", reply
            threading.Thread(target=hold_ledger, daemon=True).start()
            if not held.wait(4):
                raise AssertionError("ledger lock was not acquired")
            threading.Event().wait(max(0, deadline - time.time()))
            raise requests.ReadTimeout("offline timeout")

        def observe(job_id):
            try:
                observations.append(self.terminal(job_id))
            except BaseException as exc:
                errors.append(exc)
            finally:
                observed.set()

        def late():
            late_started.set()
            try:
                callbacks[0](reply, body, .01, 2, True)
            finally:
                late_done.set()

        with patch("showcase.request_transport.response_events", side_effect=transport):
            job_id = self.create_job()
            self.assertTrue(held.wait(5))
            observer = threading.Thread(target=observe, args=(job_id,), daemon=True)
            observer.start()
            try:
                self.assertTrue(observed.wait(max(0, deadline - time.time()) + 3),
                                "Job waited for the occupied ledger lock")
                self.assertEqual([], errors)
                before, = observations
                self.assertEqual("failed", before["status"])
                self.assertEqual(1, before["result"]["budget"]["unresolved_attempts"])
                self.assertGreater(before["result"]["budget"]["reserved_tokens"], 0)
                pending, = before["result"]["request_attempts"]
                self.assertNotEqual("not_submitted", pending.get("dispatch_status"))
                self.assertFalse(release.is_set())
                late_worker = threading.Thread(target=late, daemon=True)
                late_worker.start()
                self.assertTrue(late_started.wait(2))
            finally:
                release.set()
            self.assertTrue(late_done.wait(5))
            observer.join(2)
            late_worker.join(2)
            after = self.wait_for(lambda: (job if (job := self.job(job_id))["result"]
                ["budget"]["unresolved_attempts"] == 0 else None))
        self.assertEqual([True], sends)
        self.assertEqual(0, self.post.call_count)
        self.assertEqual(before["status"], after["status"])
        self.assertEqual(before["result"]["solver"], after["result"]["solver"])
        self.assertEqual(pending["attempt_id"], after["result"]["request_attempts"][0]["attempt_id"])
        self.assertEqual(10, after["result"]["request_attempts"][0]["usage"]["total_tokens"])


if __name__ == "__main__":
    unittest.main()
