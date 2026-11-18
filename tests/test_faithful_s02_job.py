"""S02 admission and read-only recovery at authenticated streaming Job seams."""

import unittest
from unittest.mock import patch

from requests.exceptions import ReadTimeout

from llm_client import InternChatClient
from showcase.adapters import InternStreamAdapter
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture

ENDPOINT = "http://127.0.0.1:5000/api/v1/chat/completions"


def policy(cap):
    return {
        "version": "context-capacity-v1", "profile_version": "s02-controlled-v1",
        "provider": "intern", "model": "intern-s2", "endpoint": ENDPOINT,
        "cap_source": "controlled_test_only", "cap_source_date": "2026-11-07",
        "input_cap_tokens": cap, "output_reserve_tokens": 256,
        "safety_margin_tokens": 10,
        "token_estimator_version": "utf8-bytes-per-three-v1",
    }


class FaithfulS02JobTest(StarJobFixture, unittest.TestCase):
    def open_context(self, cap):
        self.enterContext(patch.dict("os.environ", {"INTERN_API_BASE": ENDPOINT}))
        self.open_star(
            [SOLVED, POLISH, ACCEPT], stream_chunk_size=65536,
            SHOWCASE_STAR_ADAPTER=InternStreamAdapter(InternChatClient(retry=1), max_tokens=256),
            SHOWCASE_STAR_FEATURES={"context_pack": True},
            SHOWCASE_STAR_CONTEXT_CAPACITY=policy(cap),
        )

    def test_stream_job_reports_uncalibrated_pack_and_reads_do_not_dispatch(self):
        self.open_context(None)
        create_headers = self.headers()
        create_body = {"message": "1+1", "session_id": self.session, "solver_mode": "star_limited"}
        created = self.client.post("/api/agent/jobs", json=create_body, headers=create_headers)
        self.assertEqual(202, created.status_code)
        job_id = created.get_json()["job_id"]
        completed = self.terminal(job_id)
        self.assertEqual("succeeded", completed["status"], completed)
        report = self.report(job_id)
        context = report["semantics"]["context_capacity"]
        self.assertEqual("uncalibrated", context["status"])
        self.assertEqual(3, context["pack_count"])
        self.assertEqual("whole_solution_verifier", context["packs"][-1]["role"])
        self.assertEqual("s02-controlled-v1", context["packs"][-1]["profile"]["version"])
        self.assertGreater(context["packs"][-1]["serialized_utf8_bytes"], 0)
        self.assertEqual("same_artifact", report["semantics"]["binding"])
        sent = self.post.call_count
        self.app.config["SHOWCASE_STAR_CONTEXT_CAPACITY"] = policy(1)
        for _ in range(2):
            self.assertEqual("succeeded", self.job(job_id)["status"])
            self.assertEqual(context, self.report(job_id)["semantics"]["context_capacity"])
            evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
            self.assertEqual(context, evidence["semantics"]["context_capacity"])
        replay = self.client.post("/api/agent/jobs", json=create_body, headers=create_headers)
        self.assertEqual(200, replay.status_code, replay.get_json())
        self.assertEqual(job_id, replay.get_json()["job_id"])
        self.assertEqual(sent, self.post.call_count)
        self.assertEqual(3, sent)

    def test_fixed_layer_refusal_is_known_and_sends_no_http(self):
        self.open_context(1)
        job_id = self.create_job()
        completed = self.terminal(job_id)
        self.assertEqual("failed", completed["status"], completed)
        report = self.report(job_id)
        semantics = report["semantics"]
        self.assertEqual("context_capacity_exceeded", semantics["context_capacity"]["status"])
        self.assertEqual("not_reviewed", semantics["whole_review"])
        self.assertEqual("unbound", semantics["binding"])
        self.assertNotEqual("unknown", semantics["transport"])
        self.assertEqual(0, self.post.call_count)
        self.assertEqual(0, report["budget"]["reserved_tokens"])
        self.assertEqual(0, report["budget"]["http_attempts"])


    def test_whole_verifier_oversized_answer_stays_unreviewed(self):
        self.open_context(20_000)
        self.replies[:] = [SOLVED, {"solution_candidate": "x" * 100_000}, ACCEPT]
        job_id = self.create_job()
        completed = self.terminal(job_id)
        self.assertEqual("failed", completed["status"], completed)
        semantics = self.report(job_id)["semantics"]
        latest = semantics["context_capacity"]["packs"][-1]
        self.assertEqual("whole_solution_verifier", latest["role"])
        self.assertEqual("context_capacity_exceeded", latest["capacity_status"])
        self.assertEqual("not_reviewed", semantics["whole_review"])
        self.assertEqual("unbound", semantics["binding"])
        self.assertEqual(2, self.post.call_count)
        self.assertEqual([ACCEPT], self.replies)

    def test_context_metering_preserves_unknown_reservation_and_original_deadline(self):
        self.open_context(None)
        self.replies[:] = [ReadTimeout("controlled unknown outcome")]
        job_id = self.create_job()
        completed = self.terminal(job_id)
        self.assertEqual("failed", completed["status"])
        before = self.report(job_id)
        self.assertEqual("unknown", before["semantics"]["transport"])
        self.assertEqual("uncalibrated", before["semantics"]["context_capacity"]["status"])
        self.assertEqual(1, before["budget"]["unknown_attempts"])
        self.assertGreater(before["budget"]["reserved_tokens"], 0)
        resumed = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers())
        self.assertEqual(409, resumed.status_code)
        after = self.report(job_id)
        self.assertEqual(before["budget"]["reserved_tokens"], after["budget"]["reserved_tokens"])
        self.assertEqual(before["budget"]["deadline_at"], after["budget"]["deadline_at"])
        self.assertEqual(1, self.post.call_count)
        self.assertEqual([], self.replies)

if __name__ == "__main__":
    unittest.main()
