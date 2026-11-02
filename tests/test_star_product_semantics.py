"""RB04 product meaning at the authenticated Job/Run boundary (scripted HTTP)."""

import json
import time
import unittest
from threading import Event
from unittest.mock import patch

from requests.exceptions import ReadTimeout

from showcase.run_budget import RunBudgetLimits
from showcase.solver_harness.final_binding import review_record
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture


class ResultSemanticsTest(StarJobFixture, unittest.TestCase):
    def create_job(self, verification_mode="auto"):
        response = self.client.post("/api/agent/jobs", json={"message": "1+1",
            "session_id": self.session, "solver_mode": "star_limited",
            "verification_mode": verification_mode}, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        return response.get_json()["job_id"]

    def test_completed_review_is_explicit_without_upgrading_legacy_math_evidence(self):
        self.open_star([SOLVED, POLISH, ACCEPT])
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"])
        report = self.report(job_id)
        self.assertEqual("unknown", report["checks"]["status"])
        self.assertEqual("needs_review", report["checks"]["acceptance"])
        self.assertEqual({
            "version": "star-result-semantics-v1", "execution": "completed",
            "transport": "known", "whole_review": "accepted",
            "binding": "same_artifact", "formal_verification": "not_verified",
            "verification_requirement": "default",
        }, report.get("semantics"))
        run = self.client.get(f"/api/runs/{job_id}").get_json()
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertEqual(report["semantics"], job["result"]["solver"]["semantics"])
        self.assertEqual(report["semantics"], run["result"]["solver"]["semantics"])
        self.assertEqual(report["semantics"], evidence["semantics"])
        self.assertEqual(report["semantics"], evidence["report"]["semantics"])

    def test_real_unknown_stays_manual_and_never_becomes_an_llm_acceptance(self):
        self.open_star([ReadTimeout("in-flight response unknown")])
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("failed", job["status"])
        report = self.report(job_id)
        semantic = report["semantics"]
        self.assertEqual("unknown", semantic["transport"])
        self.assertEqual("not_reviewed", semantic["whole_review"])
        self.assertEqual("unbound", semantic["binding"])
        self.assertEqual("needs_review", semantic["execution"])
        self.assertEqual("needs_review", report["solver"]["solver"]["recovery"]["status"])
        self.assertEqual(1, self.post.call_count)
        self.assertGreater(report["budget"]["reserved_tokens"], 0)

    def test_running_and_canceled_execution_follow_existing_lifecycle(self):
        release = Event()

        def delayed(_context):
            release.wait(4)
            return SOLVED

        self.open_star([delayed])
        job_id = self.create_job()
        try:
            self.wait_for(lambda: self.outbound)
            self.assertEqual("running", self.job(job_id)["result"]["solver"]["semantics"]["execution"])
            self.cancel(job_id)
            self.assertEqual("canceled", self.job(job_id)["result"]["solver"]["semantics"]["execution"])
            run = self.client.get(f"/api/runs/{job_id}").get_json()
            self.assertEqual("canceled", run["result"]["solver"]["semantics"]["execution"])
        finally:
            release.set()

    def test_rewrite_retains_prior_review_but_cannot_inherit_its_binding(self):
        self.open_star([SOLVED, POLISH, ACCEPT])
        with patch("showcase.star_product_pipeline.export_result",
                   return_value={"final_response": "rewritten unreviewed answer"}):
            job_id = self.create_job()
            job = self.terminal(job_id)
        self.assertEqual("failed", job["status"])
        report = self.report(job_id)
        semantic = report["semantics"]
        self.assertEqual("accepted", semantic["whole_review"])
        self.assertEqual("artifact_changed", semantic["binding"])
        self.assertEqual("needs_review", semantic["execution"])
        self.assertEqual("known", semantic["transport"])
        self.assertEqual("unknown", report["checks"]["status"])
        self.assertEqual("1+1=2", report["checks"]["history"][0]["versions"][-1]["text"])

    def test_required_mode_keeps_extra_gate_despite_accepted_bound_llm_review(self):
        self.open_star([SOLVED, POLISH, ACCEPT])
        job_id = self.create_job("required")
        job = self.terminal(job_id)
        self.assertEqual("failed", job["status"])
        report = self.report(job_id)
        semantic = report["semantics"]
        self.assertEqual("needs_review", semantic["execution"])
        self.assertEqual("required_unmet", semantic["verification_requirement"])
        self.assertEqual("accepted", semantic["whole_review"])
        self.assertEqual("same_artifact", semantic["binding"])
        self.assertEqual("not_verified", semantic["formal_verification"])
        self.assertEqual("known", semantic["transport"])
        self.assertEqual("verification_needs_review", job["error"])
        self.assertEqual(3, self.post.call_count)

    def test_local_check_appends_scope_without_erasing_whole_review_meaning(self):
        self.open_star([SOLVED, POLISH, ACCEPT])
        job_id = self.create_job()
        self.terminal(job_id)
        before = self.report(job_id)
        response = self.client.post(f"/api/agent/jobs/{job_id}/polynomial-check", json={
            "schema_version": 1, "variable": "x", "coefficients": ["1", "-1"],
            "domain": {"kind": "real"}, "candidates": ["1"],
        }, headers=self.headers())
        self.assertEqual(200, response.status_code, response.get_json())
        after = self.report(job_id)
        self.assertEqual(before["semantics"], after["semantics"])
        self.assertEqual(before["checks"]["history"], after["checks"]["history"][:1])
        self.assertEqual(2, len(after["checks"]["history"]))
        self.assertEqual("polynomial_candidates", after["checks"]["history"][-1]["scope"])
        self.assertEqual("whole_solution_llm_review", after["checks"]["history"][0]["scope"])
        self.assertEqual("unknown", after["checks"]["status"])
        self.assertEqual("needs_review", after["checks"]["acceptance"])
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertEqual(after["semantics"], evidence["semantics"])
        self.assertEqual(after["checks"], evidence["verification"])
        self.assertEqual(3, self.post.call_count)

    def test_terminal_sse_agrees_with_report_and_does_not_claim_needs_review(self):
        self.open_star([SOLVED, POLISH, ACCEPT])
        job_id = self.create_job()
        self.terminal(job_id)
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith("data: ")]
        final = next(event for event in events if event["type"] == "final_result")
        self.assertEqual(self.report(job_id)["semantics"], final.get("semantics"))
        self.assertEqual("star_completed_llm_reviewed", final["message"])

    def test_rejected_whole_review_is_known_and_does_not_accept_the_answer(self):
        self.open_star([SOLVED, POLISH, {"verdict": "REJECT", "reason": "missing explanation"}])
        job_id = self.create_job()
        self.assertEqual("failed", self.terminal(job_id)["status"])
        semantic = self.report(job_id)["semantics"]
        self.assertEqual("rejected", semantic["whole_review"])
        self.assertEqual("known", semantic["transport"])
        self.assertEqual("needs_review", semantic["execution"])

    def test_forged_source_cannot_look_like_accepted_bound_output(self):
        self.open_star([SOLVED, POLISH, ACCEPT])

        def corrupt(*args, **kwargs):
            record = review_record(*args, **kwargs)
            record["source"]["call_id"] = "forged:whole-review"
            return record

        with patch("showcase.solver_harness.review.review_record", side_effect=corrupt):
            job_id = self.create_job()
            self.assertEqual("failed", self.terminal(job_id)["status"])
        semantic = self.report(job_id)["semantics"]
        self.assertEqual("invalid_source", semantic["whole_review"])
        self.assertEqual("unbound", semantic["binding"])
        self.assertEqual("known", semantic["transport"])
        self.assertEqual("needs_review", semantic["execution"])

    def test_deadline_failure_remains_failed_in_execution_projection(self):
        def late(_context):
            time.sleep(.6)
            return SOLVED

        self.open_star([late], SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_runtime_seconds=.5))
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("failed", job["status"])
        self.assertEqual("run_deadline_exhausted", job["error"])
        run = self.client.get(f"/api/runs/{job_id}").get_json()
        self.assertEqual("FAILED", run["status"])
        self.assertEqual("failed", run["result"]["solver"]["semantics"]["execution"])
        self.assertEqual("failed", self.report(job_id)["semantics"]["execution"])
