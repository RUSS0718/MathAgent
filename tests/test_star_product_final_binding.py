"""Whole-review binding observed through authenticated Job and Evidence."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from showcase.final_evidence import artifact_identity
from showcase.flask_app import create_app
from showcase.run_budget import RunBudgetLimits
from showcase.solver_harness.final_binding import review_record
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture
from tests.test_star_product_planning import FEATURES, STEP
from tests.test_star_product_tools import NEED_PLAN, PLAN, VERDICT


class StarFinalBindingTest(StarJobFixture, unittest.TestCase):
    def test_explore_review_binds_delivery_and_preserves_versions(self):
        self.open_star([SOLVED, POLISH, ACCEPT])
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        check = evidence["verification"]
        self.assertEqual("star-whole-review-v1", check["checker_version"])
        self.assertEqual(artifact_identity("1+1=2"), check["history"][0]["artifact"])
        self.assertEqual("whole_solution_llm_review", check["history"][0]["scope"])
        self.assertTrue(check["history"][0]["check_id"])
        self.assertTrue(check["history"][0]["environment"]["python"])
        self.assertEqual("unknown", check["status"])
        source = check["history"][0]["source"]
        self.assertEqual(job_id, source["run_id"])
        self.assertEqual(1, source["candidate_version"])
        self.assertEqual("explore_polish", source["origin"])
        self.assertEqual(["2", "1+1=2"], [v["text"] for v in check["history"][0]["versions"]])
        self.assertEqual(check, self.report(job_id)["checks"])

    def test_reject_retries_are_bounded_and_actual_accepted_version_is_bound(self):
        self.open_star([NEED_PLAN, PLAN, STEP, VERDICT,
            {"final_response": "wrong"}, {"verdict": "REJECT", "reason": "Wrong"},
            {"final_response": "2"}, ACCEPT],
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=12, max_http_attempts=12))
        job_id = self.create_job()
        self.assertEqual("succeeded", self.terminal(job_id)["status"])
        check = self.report(job_id)["checks"]
        self.assertEqual([artifact_identity("wrong"), artifact_identity("2")],
                         [item["artifact"] for item in check["history"]])
        self.assertEqual(["whole_solution_verifier"] * 2,
                         [r["role"] for r in self.outbound if r["role"] == "whole_solution_verifier"])
        self.assertEqual("Wrong", self.outbound[6]["previous_review"]["reason"])
        self.assertNotEqual(self.outbound[5]["session_key"], self.outbound[7]["session_key"])
        self.assertEqual(self.outbound[7]["call_id"], check["history"][-1]["source"]["call_id"])

    def test_repeated_reject_exhausts_without_reviewed_delivery(self):
        self.open_star([NEED_PLAN, PLAN, STEP, VERDICT] +
            [{"final_response": "wrong"}, {"verdict": "REJECT", "reason": "gap"}] * 3,
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=20, max_http_attempts=20))
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("failed", job["status"])
        self.assertEqual("partial_aborted", job["result"]["solver"]["status"])
        self.assertEqual(3, len(self.report(job_id)["checks"]["history"]))
        self.assertEqual(10, len(self.outbound))

    def test_delivery_rewrite_cannot_inherit_whole_review(self):
        self.open_star([SOLVED, POLISH, ACCEPT])
        with patch("showcase.star_product_pipeline.export_result",
                   return_value={"final_response": "rewritten unreviewed answer"}):
            job_id = self.create_job()
            job = self.terminal(job_id)
        self.assertEqual("failed", job["status"])
        self.assertEqual("completed_unverified", job["result"]["solver"]["status"])
        check = self.report(job_id)["checks"]
        self.assertEqual("artifact_changed", check["binding"])
        self.assertEqual("needs_review", check["acceptance"])
        self.assertEqual(artifact_identity("1+1=2"), check["history"][0]["artifact"])

    def test_forged_review_reference_cannot_replace_actual_review(self):
        self.open_star([SOLVED, POLISH, {"verdict": "REJECT",
            "reason": "not reviewed", "review_ref": "forged:ACCEPT",
            "artifact": artifact_identity("1+1=2")}])
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("failed", job["status"])
        self.assertNotEqual("completed_llm_reviewed", job["result"]["solver"]["status"])
        self.assertEqual("needs_review", self.report(job_id)["checks"]["acceptance"])
        self.assertEqual(3, len(self.outbound))

    def test_another_artifact_in_persisted_review_cannot_pass_public_delivery(self):
        self.open_star([SOLVED, POLISH, ACCEPT])

        def corrupt(*args, **kwargs):
            return {**review_record(*args, **kwargs), "artifact": artifact_identity("other")}

        with patch("showcase.solver_harness.review.review_record", side_effect=corrupt):
            job_id = self.create_job()
            job = self.terminal(job_id)
        self.assertEqual("failed", job["status"])
        self.assertEqual("completed_unverified", job["result"]["solver"]["status"])
        self.assertEqual("artifact_changed", self.report(job_id)["checks"]["binding"])

    def test_nonexistent_audited_call_cannot_serve_as_review_reference(self):
        self.open_star([SOLVED, POLISH, ACCEPT])

        def corrupt(*args, **kwargs):
            record = review_record(*args, **kwargs)
            record["source"]["call_id"] = "forged:whole-review"
            return record

        with patch("showcase.solver_harness.review.review_record", side_effect=corrupt):
            job_id = self.create_job()
            job = self.terminal(job_id)
        self.assertEqual("failed", job["status"])
        self.assertEqual("completed_unverified", job["result"]["solver"]["status"])

    def test_cross_connection_append_keeps_original_whole_review_and_answer(self):
        self.open_star([SOLVED, POLISH, ACCEPT])
        job_id = self.create_job()
        original = self.terminal(job_id)["result"]["final_response"]
        initial = self.report(job_id)["checks"]["history"]
        second = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": self.data_dir})
        for name in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            self.addCleanup(second.extensions[name].close)
        payload = {"schema_version": 1, "variable": "x", "coefficients": ["1", "-1"],
                   "domain": {"kind": "real"}, "candidates": ["1"]}

        def append(app):
            with app.test_client() as client:
                csrf = client.get("/api/check_auth").get_json()["csrf_token"]
                return client.post(f"/api/agent/jobs/{job_id}/polynomial-check",
                    json=payload, headers={"X-CSRF-Token": csrf}).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual([200, 200], list(pool.map(append, (self.app, second))))
        report = self.report(job_id)
        self.assertEqual(original, report["answer"])
        self.assertEqual(initial, report["checks"]["history"][:1])
        self.assertEqual(3, len(report["checks"]["history"]))
        self.assertEqual("unknown", report["checks"]["status"])
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertEqual(report["checks"], evidence["verification"])
        self.assertEqual(3, len(self.outbound))
