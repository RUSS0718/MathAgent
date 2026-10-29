"""#99/#100: bounded safe retry and opt-in serialization repair via public Jobs."""

import json
import os
import time
import unittest
from collections import Counter
from unittest.mock import patch

import requests

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter, InternStreamAdapter
from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, POLISH, SOLVED, RawProviderContent, StarJobFixture
from tests.test_star_product_planning import FEATURES


class StarRetrySerializationIntegrationTest(StarJobFixture, unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {"INTERN_API_KEY": "offline-99-100"}))
        real_sleep = time.sleep
        self.waits = []

        def wait(seconds):
            # Preserve the fixture's short polling sleeps; skip only retry backoff.
            if seconds >= 1:
                self.waits.append(seconds)
            else:
                real_sleep(seconds)

        self.enterContext(patch("llm_client.time.sleep", side_effect=wait))

    def open_combined(self, streaming, replies):
        """Use the existing finite HTTP fixture with both policies explicitly enabled."""
        client = InternChatClient(timeout=180, retry=1, safe_retry_attempts=6)
        client.api_base = "http://127.0.0.1:1/offline-99-100"
        adapter = (InternStreamAdapter if streaming else InternModelAdapter)(client, max_tokens=256)
        self.open_star(
            replies, SHOWCASE_STAR_ADAPTER=adapter,
            SHOWCASE_STAR_FEATURES={**FEATURES, "serialization_repair": True},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=4, max_http_attempts=14),
        )

    def test_six_attempt_retries_and_same_value_repair_do_not_multiply(self):
        raw = "```json\n" + json.dumps(SOLVED) + "\n```"
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                self.waits.clear()
                self.open_combined(streaming,
                    [requests.ConnectTimeout()] * 5 + [RawProviderContent(raw)]
                    + [requests.ConnectTimeout()] * 5 + [SOLVED, POLISH, ACCEPT])
                job_id = self.create_job()
                job = self.terminal(job_id)
                self.assertEqual("succeeded", job["status"], job)
                self.assertEqual("1+1=2", job["result"]["final_response"])
                budget = job["result"]["budget"]
                self.assertEqual((4, 14, 0, 0, 0, 40), (
                    budget["logical_calls"], budget["http_attempts"],
                    budget["unknown_attempts"], budget["unresolved_attempts"],
                    budget["reserved_tokens"], budget["charged_tokens"]))
                self.assertEqual({"prompt_tokens": 28, "completion_tokens": 12,
                                  "total_tokens": 40}, budget["provider_known"])
                self.assertEqual(14, self.post.call_count)
                self.assertEqual(14, len(self.outbound))
                self.assertEqual([], self.replies)
                self.assertEqual([1, 2, 4, 8, 15] * 2, self.waits)

                attempts = job["result"]["request_attempts"]
                self.assertEqual(14, len(attempts))
                self.assertEqual(14, len({a["attempt_id"] for a in attempts}))
                self.assertEqual([1, 1, 6, 6], sorted(Counter(
                    a["logical_call_id"] for a in attempts).values()))
                self.assertTrue(all(a["retry_limit"] == 6 for a in attempts))
                self.assertTrue(all(a["provider_stream"] == streaming for a in attempts))
                explore = [a for a in attempts if a["role"] == "explore"]
                self.assertEqual([1, 2, 3, 4, 5, 6] * 2,
                                 [a["attempt_index"] for a in explore])
                self.assertEqual(1, len({a["logical_call_id"] for a in explore[:6]}))
                self.assertEqual(1, len({a["logical_call_id"] for a in explore[6:]}))
                self.assertNotEqual(explore[0]["logical_call_id"], explore[6]["logical_call_id"])
                self.assertEqual(["not_submitted"] * 5 + ["transport_observed"]
                                 + ["not_submitted"] * 5 + ["transport_observed"],
                                 [a["dispatch_status"] for a in explore])

                original_id = self.outbound[0]["call_id"]
                self.assertEqual({original_id}, {r["call_id"] for r in self.outbound[:6]})
                self.assertEqual({original_id + ":serialization-1"},
                                 {r["call_id"] for r in self.outbound[6:12]})
                for repair in self.outbound[6:12]:
                    self.assertEqual(raw, repair["visible_reply"])
                    self.assertEqual([], repair["allowed_tools"])

    def test_unknown_repair_keeps_pending_identity_reservation_and_deadlines(self):
        raw = "```json\n" + json.dumps(SOLVED) + "\n```"
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                self.waits.clear()
                self.open_combined(streaming,
                    [requests.ConnectTimeout()] * 5 + [RawProviderContent(raw)]
                    + [requests.ConnectTimeout()] * 2 + [requests.ReadTimeout("unknown")]
                    + [SOLVED, POLISH, ACCEPT])
                job_id = self.create_job()
                first = self.terminal(job_id)
                self.assertEqual("failed", first["status"], first)
                budget = first["result"]["budget"]
                self.assertEqual((2, 9, 1, 1), (
                    budget["logical_calls"], budget["http_attempts"],
                    budget["unknown_attempts"], budget["unresolved_attempts"]))
                self.assertEqual({"prompt_tokens": 7, "completion_tokens": 3,
                                  "total_tokens": 10}, budget["provider_known"])
                self.assertGreater(budget["reserved_tokens"], 256)
                self.assertEqual(budget["reserved_tokens"] + 10, budget["charged_tokens"])
                self.assertEqual([1, 2, 4, 8, 15, 1, 2], self.waits)

                recovery = first["result"]["solver"]["recovery"]
                repair_id = self.outbound[0]["call_id"] + ":serialization-1"
                self.assertEqual("needs_review", recovery["status"])
                self.assertEqual([{"call_id": repair_id, "status": "unknown_outcome",
                                   "role": "explore"}], recovery["unknown_calls"])
                self.assertEqual({repair_id}, {r["call_id"] for r in self.outbound[6:]})
                self.assertEqual(raw, self.outbound[-1]["visible_reply"])
                attempts = first["result"]["request_attempts"]
                self.assertEqual(9, len({a["attempt_id"] for a in attempts}))
                self.assertEqual([3, 6], sorted(Counter(
                    a["logical_call_id"] for a in attempts).values()))
                self.assertEqual([1, 2, 3, 4, 5, 6, 1, 2, 3],
                                 [a["attempt_index"] for a in attempts])
                pending = attempts[-1]
                self.assertEqual("unknown", pending["metering_status"])
                self.assertEqual(6, pending["retry_limit"])

                for route in (f"/api/agent/jobs/{job_id}/resume", f"/api/runs/{job_id}/resume"):
                    rejected = self.client.post(route, json={}, headers=self.headers())
                    self.assertEqual(409, rejected.status_code, rejected.get_json())
                final = self.job(job_id)
                self.assertEqual("failed", final["status"])
                self.assertEqual(recovery, final["result"]["solver"]["recovery"])
                self.assertEqual(attempts, final["result"]["request_attempts"])
                evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
                report = self.report(job_id)
                for observed in (final["result"]["budget"], evidence["budget"]):
                    for key in ("logical_calls", "http_attempts", "unknown_attempts",
                                "unresolved_attempts", "reserved_tokens", "charged_tokens",
                                "provider_known", "deadline_at"):
                        self.assertEqual(budget[key], observed[key], key)
                for recorded in (report["request_attempts"], evidence["request_attempts"]):
                    self.assertEqual(9, len(recorded))
                    self.assertEqual(pending, recorded[-1])
                self.assertEqual(9, self.post.call_count)
                self.assertEqual(9, len(self.outbound))
                self.assertEqual([SOLVED, POLISH, ACCEPT], self.replies)
                self.assertEqual([1, 2, 4, 8, 15, 1, 2], self.waits)


if __name__ == "__main__":
    unittest.main()
