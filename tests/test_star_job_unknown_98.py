"""Issue #98: unknown outcome and missing metering through the public Job."""

import json
import os
import threading
import time
import unittest
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternStreamAdapter
from showcase.star_experiment_policy import ExperimentRunPolicy
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture


class PublicJobUnknownTest(StarJobFixture, unittest.TestCase):
    def test_late_stream_finished_without_usage_keeps_result_and_reservation(self):
        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            adapter = InternStreamAdapter(InternChatClient(timeout=2, retry=3))
        policy = ExperimentRunPolicy(time.time() + 8, phase_deadline_at=time.time() + 1.2)
        self.open_star([], SHOWCASE_STAR_ADAPTER=adapter,
                       SHOWCASE_STAR_EXPERIMENT_POLICY=policy,
                       SHOWCASE_STAR_FEATURES={"strict_completion": True})
        release = threading.Event()
        self.addCleanup(release.set)

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

            def close(self):
                pass

            def iter_content(self, chunk_size=1):
                packet = {"choices": [{"delta": {"content": json.dumps(SOLVED)},
                          "finish_reason": "stop"}]}
                yield ("data: " + json.dumps(packet) + "\n\ndata: [DONE]\n\n").encode()

        def delayed(*_args, **_kwargs):
            release.wait(2.5)
            return Reply()

        self.post.side_effect = delayed
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("needs_review", job["result"]["solver"]["recovery"]["status"])
        self.assertEqual(1, job["result"]["budget"]["unresolved_attempts"])
        original_id = job["result"]["request_attempts"][0]["attempt_id"]
        release.set()
        settled = self.wait_for(lambda: (snapshot if (snapshot := self.job(job_id))
            ["result"]["budget"]["unresolved_attempts"] == 0 else None))
        self.assertEqual("failed", settled["status"])
        self.assertEqual(job["result"]["solver"], settled["result"]["solver"])
        self.assertEqual(1, self.post.call_count)
        self.assertEqual(original_id, settled["result"]["request_attempts"][0]["attempt_id"])
        self.assertEqual("unknown", settled["result"]["request_attempts"][0]["metering_status"])
        self.assertGreater(settled["result"]["budget"]["reserved_tokens"], 0)

    def test_completed_reply_missing_usage_keeps_budget_unknown_not_outcome(self):
        self.open_star([SOLVED, POLISH, ACCEPT],
                       SHOWCASE_STAR_FEATURES={"strict_completion": True})
        original = self.post.side_effect

        def no_usage(*args, **kwargs):
            response = original(*args, **kwargs)
            body = response.json()
            del body["usage"]
            response.iter_content = lambda **_kwargs: iter([json.dumps(body).encode()])
            return response

        self.post.side_effect = no_usage
        job = self.terminal(self.create_job())
        self.assertEqual("succeeded", job["status"])
        self.assertEqual(3, self.post.call_count)
        budget = job["result"]["budget"]
        self.assertEqual(3, budget["unknown_attempts"])
        self.assertEqual(0, budget["unresolved_attempts"])
        self.assertGreater(budget["reserved_tokens"], 0)
        self.assertIsNone(budget["provider_known"]["total_tokens"])
        for attempt in job["result"]["request_attempts"]:
            self.assertEqual("success", attempt["status"])
            self.assertEqual("stop", attempt["finish_reason"])
            self.assertEqual("unknown", attempt["metering_status"])
            self.assertIsNone(attempt["usage"]["total_tokens"])

    def test_empty_choices_with_usage_keeps_missing_finish_reservation(self):
        self.open_star([], retry=3, SHOWCASE_STAR_FEATURES={"strict_completion": True})

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

            def close(self):
                pass

            def iter_content(self, chunk_size=1):
                yield json.dumps({"choices": [], "usage": {"prompt_tokens": 7,
                    "completion_tokens": 3, "total_tokens": 10}}).encode()

        self.post.side_effect = lambda *_args, **_kwargs: Reply()
        job = self.terminal(self.create_job())
        budget = job["result"]["budget"]
        attempt, = job["result"]["request_attempts"]
        self.assertEqual("failed", job["status"])
        self.assertEqual("needs_review", job["result"]["solver"]["recovery"]["status"])
        self.assertEqual(1, self.post.call_count)
        self.assertEqual(1, budget["unresolved_attempts"])
        self.assertEqual(budget["local_input_estimate"] + 256, budget["reserved_tokens"])
        self.assertEqual(10, attempt["usage"]["total_tokens"])
        self.assertEqual("missing_finish_reason", attempt["error_category"])
    def test_unconfirmed_partial_usage_does_not_double_charge_original_reservation(self):
        self.open_star([], retry=3, SHOWCASE_STAR_FEATURES={"strict_completion": True})

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

            def close(self):
                pass

            def iter_content(self, chunk_size=1):
                yield json.dumps({"choices": [{"message": {"content": json.dumps(SOLVED)}}],
                                  "usage": {"prompt_tokens": 7}}).encode()

        self.post.side_effect = lambda *_args, **_kwargs: Reply()
        job = self.terminal(self.create_job())
        budget = job["result"]["budget"]
        self.assertEqual("needs_review", job["result"]["solver"]["recovery"]["status"])
        self.assertEqual(1, self.post.call_count)
        self.assertEqual(7, budget["provider_known"]["prompt_tokens"])
        self.assertIsNone(budget["provider_known"]["completion_tokens"])
        self.assertEqual(budget["local_input_estimate"] + 256, budget["reserved_tokens"])
        self.assertEqual(budget["reserved_tokens"], budget["charged_tokens"])

    def test_known_usage_above_original_estimate_cannot_lower_unknown_bound(self):
        self.open_star([], retry=3, SHOWCASE_STAR_FEATURES={"strict_completion": True})

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

            def close(self):
                pass

            def iter_content(self, chunk_size=1):
                yield json.dumps({"choices": [{"message": {"content": json.dumps(SOLVED)}}],
                                  "usage": {"prompt_tokens": 100000}}).encode()

        self.post.side_effect = lambda *_args, **_kwargs: Reply()
        job = self.terminal(self.create_job())
        budget = job["result"]["budget"]
        self.assertLess(budget["local_input_estimate"], 100000)
        self.assertEqual(budget["local_input_estimate"] + 256, budget["reserved_tokens"])
        self.assertEqual(100000 + 256, budget["charged_tokens"])

    def test_stream_without_done_stops_public_job_and_reserves_known_usage(self):
        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            adapter = InternStreamAdapter(InternChatClient(timeout=2, retry=3))
        self.open_star([], SHOWCASE_STAR_ADAPTER=adapter,
                       SHOWCASE_STAR_FEATURES={"strict_completion": True})

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

            def close(self):
                pass

            def iter_content(self, chunk_size=1):
                packet = {"choices": [{"delta": {"content": json.dumps(SOLVED)},
                          "finish_reason": "stop"}], "usage": {"prompt_tokens": 7,
                          "completion_tokens": 3, "total_tokens": 10}}
                yield ("data: " + json.dumps(packet) + "\n\n").encode()

        self.post.side_effect = lambda *_args, **_kwargs: Reply()
        job = self.terminal(self.create_job())
        self.assertEqual("failed", job["status"])
        self.assertEqual("needs_review", job["result"]["solver"]["recovery"]["status"])
        self.assertEqual(1, self.post.call_count)
        budget = job["result"]["budget"]
        self.assertEqual(1, budget["unresolved_attempts"])
        self.assertGreater(budget["reserved_tokens"], 0)
        self.assertEqual(10, budget["provider_known"]["total_tokens"])
        self.assertEqual(budget["local_input_estimate"] + 16384, budget["reserved_tokens"])
        self.assertEqual(budget["reserved_tokens"], budget["charged_tokens"])
        attempt = job["result"]["request_attempts"][0]
        self.assertEqual("missing_stream_terminal", attempt["error_category"])
        self.assertEqual("known", attempt["metering_status"])


if __name__ == "__main__":
    unittest.main()
