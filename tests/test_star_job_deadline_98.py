"""Issue #98: trusted deadlines through the authenticated public Job boundary."""

import json
import threading
import time
import unittest

from showcase.run_budget import RunBudgetLimits
from showcase.star_experiment_policy import ExperimentRunPolicy
from tests.star_product_support import SOLVED, StarJobFixture


class PublicJobDeadlineTest(StarJobFixture, unittest.TestCase):
    def test_buffered_complete_reply_reconciles_if_job_consumer_misses_deadline(self):
        policy = ExperimentRunPolicy(time.time() + 8)
        self.open_star([], retry=3, SHOWCASE_STAR_EXPERIMENT_POLICY=policy,
                       SHOWCASE_STAR_FEATURES={"strict_completion": True})
        reader_finished = threading.Event()

        class Reply:
            status_code = 200

            def raise_for_status(self):
                if not reader_finished.wait(2):
                    raise AssertionError("reader did not buffer the complete response")
                time.sleep(max(0, phase_deadline - time.time()) + .1)

            def close(self):
                reader_finished.set()

            def iter_content(self, chunk_size=1):
                yield json.dumps({"choices": [{"finish_reason": "stop", "message": {
                    "content": json.dumps(SOLVED)}}], "usage": {"prompt_tokens": 7,
                    "completion_tokens": 3, "total_tokens": 10}}).encode()

        self.post.side_effect = lambda *_args, **_kwargs: Reply()
        phase_deadline = time.time() + 1.2
        policy.phase_deadline_at = phase_deadline
        job = self.terminal(self.create_job())
        self.assertTrue(reader_finished.is_set())
        self.assertEqual("failed", job["status"])
        self.assertEqual("needs_review", job["result"]["solver"]["recovery"]["status"])
        self.assertEqual(1, self.post.call_count)
        self.assertEqual(1, job["result"]["budget"]["http_attempts"])
        settled = self.wait_for(lambda: (snapshot if (snapshot := self.job(job["job_id"]))
            ["result"]["budget"]["provider_known"]["total_tokens"] == 10 else None))
        self.assertEqual("failed", settled["status"])
        self.assertEqual(job["result"]["solver"], settled["result"]["solver"])
        self.assertEqual(0, settled["result"]["budget"]["reserved_tokens"])
        attempt = settled["result"]["request_attempts"][0]
        self.assertEqual("success", attempt["status"])
        self.assertAlmostEqual(phase_deadline, attempt["deadline_at"], delta=0.08)

    def test_run_deadline_stops_public_job_with_unknown_reservation(self):
        policy = ExperimentRunPolicy(time.time() + 8, phase_deadline_at=time.time() + 8)
        self.open_star([], retry=3, SHOWCASE_STAR_EXPERIMENT_POLICY=policy,
                       SHOWCASE_STAR_FEATURES={"strict_completion": True},
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_runtime_seconds=1.2))
        release = threading.Event()
        self.addCleanup(release.set)
        requests_seen = []

        def delayed(*_args, **_kwargs):
            requests_seen.append(True)
            release.wait(2.5)
            raise OSError("offline transport closed")

        self.post.side_effect = delayed
        job = self.terminal(self.create_job())
        self.assertEqual("failed", job["status"])
        self.assertEqual("needs_review", job["result"]["solver"]["recovery"]["status"])
        self.assertEqual(1, len(requests_seen))
        self.assertEqual(1, job["result"]["budget"]["unresolved_attempts"])
        self.assertGreater(job["result"]["budget"]["reserved_tokens"], 0)
        attempts = job["result"]["request_attempts"]
        self.assertEqual(1, len(attempts))
        self.assertEqual("timeout", attempts[0]["error_category"])
        self.assertAlmostEqual(job["result"]["budget"]["deadline_at"],
                               attempts[0]["deadline_at"], delta=0.08)
    def test_batch_deadline_stops_public_job_with_unknown_reservation(self):
        batch_deadline = time.time() + 1.2
        policy = ExperimentRunPolicy(batch_deadline, phase_deadline_at=time.time() + 8)
        self.open_star([], retry=3, SHOWCASE_STAR_EXPERIMENT_POLICY=policy,
                       SHOWCASE_STAR_FEATURES={"strict_completion": True})
        release = threading.Event()
        self.addCleanup(release.set)
        requests_seen = []

        def delayed(*_args, **_kwargs):
            requests_seen.append(True)
            release.wait(2.5)
            raise OSError("offline transport closed")

        self.post.side_effect = delayed
        job = self.terminal(self.create_job())
        self.assertEqual("failed", job["status"])
        self.assertEqual("needs_review", job["result"]["solver"]["recovery"]["status"])
        self.assertEqual(1, len(requests_seen))
        self.assertEqual(1, job["result"]["budget"]["unresolved_attempts"])
        self.assertGreater(job["result"]["budget"]["reserved_tokens"], 0)
        attempts = job["result"]["request_attempts"]
        self.assertEqual(1, len(attempts))
        self.assertEqual("timeout", attempts[0]["error_category"])
        self.assertAlmostEqual(batch_deadline, attempts[0]["deadline_at"], delta=0.08)
    def test_phase_deadline_reaches_inflight_request_and_preserves_unknown(self):
        policy = ExperimentRunPolicy(time.time() + 8)
        self.open_star([], retry=3, SHOWCASE_STAR_EXPERIMENT_POLICY=policy,
                       SHOWCASE_STAR_FEATURES={"strict_completion": True})
        release = threading.Event()
        self.addCleanup(release.set)
        requests_seen = []

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

            def close(self):
                pass

            def iter_content(self, chunk_size=1):
                yield json.dumps({"choices": [{"finish_reason": "stop", "message": {
                    "content": json.dumps(SOLVED)}}], "usage": {"prompt_tokens": 7,
                    "completion_tokens": 3, "total_tokens": 10}}).encode()

        def delayed(*_args, **_kwargs):
            requests_seen.append(True)
            release.wait(2.5)
            return Reply()

        self.post.side_effect = delayed
        phase_deadline = time.time() + 1.2
        policy.phase_deadline_at = phase_deadline
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("failed", job["status"])
        self.assertEqual("needs_review", job["result"]["solver"]["recovery"]["status"])
        self.assertEqual(1, len(requests_seen))
        self.assertEqual(1, job["result"]["budget"]["unresolved_attempts"])
        self.assertGreater(job["result"]["budget"]["reserved_tokens"], 0)
        attempts = job["result"]["request_attempts"]
        self.assertEqual(1, len(attempts))
        self.assertEqual("timeout", attempts[0]["error_category"])
        self.assertAlmostEqual(phase_deadline, attempts[0]["deadline_at"], delta=0.08)
        original_id = attempts[0]["attempt_id"]
        solver_before = job["result"]["solver"]
        answer_before = job["result"].get("final_response")
        release.set()
        settled = self.wait_for(lambda: (snapshot if (snapshot := self.job(job_id))
            ["result"]["budget"]["provider_known"]["total_tokens"] == 10 else None))
        self.assertEqual("failed", settled["status"])
        self.assertEqual(solver_before, settled["result"]["solver"])
        self.assertEqual(answer_before, settled["result"].get("final_response"))
        self.assertEqual(1, len(requests_seen))
        self.assertEqual(original_id, settled["result"]["request_attempts"][0]["attempt_id"])
        self.assertEqual(attempts[0]["deadline_at"],
                         settled["result"]["request_attempts"][0]["deadline_at"])


if __name__ == "__main__":
    unittest.main()
