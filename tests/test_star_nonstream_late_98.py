"""Public Job regressions for non-stream late settlement deadlines."""

import json
import threading
import time
import unittest
from unittest.mock import patch

import requests

from showcase.run_budget import RunBudgetLedger
from tests.star_product_support import SOLVED, StarJobFixture


class NonstreamLateTest(StarJobFixture, unittest.TestCase):
    def test_slow_late_sqlite_settlement_does_not_delay_timeout(self):
        self.open_star([], SHOWCASE_STAR_FEATURES={"strict_completion": True})
        entered, release, finished = (threading.Event() for _ in range(3))
        self.addCleanup(release.set)
        original = RunBudgetLedger.settle
        sends = []

        class Reply:
            status_code = 200

        def slow_settle(ledger, run_id, attempt_id, event):
            if event.get("status") == "success":
                entered.set()
                if not release.wait(3):
                    raise AssertionError("late settlement not released")
            return original(ledger, run_id, attempt_id, event)

        def transport(_url, *, on_late_response, **_kwargs):
            sends.append(True)
            body = json.dumps({"choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps(SOLVED)}}], "usage": {"prompt_tokens": 7,
                "completion_tokens": 3, "total_tokens": 10}}).encode()

            def late():
                try:
                    on_late_response(Reply(), body, .01, .2, True)
                finally:
                    finished.set()

            threading.Thread(target=late, daemon=True).start()
            if not entered.wait(2):
                raise AssertionError("late settlement not started")
            raise requests.ReadTimeout("offline deadline")
            yield

        with (patch("showcase.request_transport.response_events", side_effect=transport),
              patch.object(RunBudgetLedger, "settle", slow_settle)):
            job_id = self.create_job()
            self.assertTrue(entered.wait(2))
            deadline = time.monotonic() + 1.2
            while time.monotonic() < deadline:
                job = self.job(job_id)
                if job["status"] in {"failed", "succeeded", "canceled"}:
                    break
                time.sleep(.01)
            self.assertEqual("failed", job["status"], "deadline must not await late SQLite")
            self.assertFalse(finished.is_set())
            release.set()
            self.assertTrue(finished.wait(2))
            settled = self.job(job_id)
        self.assertEqual([True], sends)
        self.assertEqual("failed", settled["status"])
        self.assertEqual(0, settled["result"]["budget"]["unresolved_attempts"])
        self.assertEqual("success", settled["result"]["request_attempts"][0]["status"])


if __name__ == "__main__":
    unittest.main()