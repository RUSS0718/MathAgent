"""F6 delivery contracts through the public presentation artifact seam."""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from showcase.presentation import (
    build_presentation,
    failed_presentation,
    presentation_snapshot,
    revalidate,
)
from showcase.solver_harness import SolverHarness
from showcase.star_product_candidates import candidate_projection
from showcase.star_product_pipeline import projection
from tests import test_faithful_s07_graph as s07
from tests import test_s06_presentation as s06


def evidence_job():
    job = s06.job_fixture()
    job["result"]["presentation_policy_version"] = "faithful-output-v2"
    return job


class FaithfulF6PresentationTest(unittest.TestCase):
    def test_persisted_graph_claim_exposes_proposition_and_inference_only_for_exact_public_excerpt(self):
        with SolverHarness(config={"features": {"proof_graph": True}}) as harness:
            run = harness.solve("problem")
            patch = s07.FaithfulS07GraphTest._ledger_patch(run, [
                ("a", "1+1=2", "arithmetic", []),
                ("b", "PRIVATE_UNDELIVERED_CLAIM", "private scope", []),
            ])
            run = s07.FaithfulS07GraphTest._commit(harness, run, "f6-seed", patch)
            job = evidence_job()
            answer = "Known result: 1+1=2. Remaining goal unresolved."
            job["result"]["final_response"] = answer
            job["result"]["solver"] = projection(run, answer=answer)
            artifact = build_presentation(presentation_snapshot(job), "solve")
            patch["verified_results_ledger"][0].update(valid=False, invalidated=True)
            run = s07.FaithfulS07GraphTest._commit(harness, run, "f6-withdraw", patch)
            job["result"]["solver"] = projection(run, answer=answer)
            withdrawn = presentation_snapshot(job)
        graph_sources = [source for source in artifact["sources"]
                         if source.get("kind") in {"Proposition", "Inference"}]
        self.assertEqual({"Proposition", "Inference"}, {source["kind"] for source in graph_sources})
        self.assertTrue(all(source["graph_version"] == 2 for source in graph_sources))
        self.assertNotIn("PRIVATE_UNDELIVERED_CLAIM", str(artifact))
        self.assertEqual(1, len(artifact["delivery"]["verified_claims"]))
        self.assertEqual("1+1=2", artifact["delivery"]["verified_claims"][0]["text"])
        self.assertEqual([], withdrawn["verified_claims"])
        self.assertEqual("needs_review", revalidate(artifact, withdrawn)["status"])

    def test_l2_evidence_has_a_versioned_target_reference_without_upgrading_original_answer(self):
        job = evidence_job()
        job["result"]["solver"]["formal_verification"] = {
            "status": "solved", "grade": "L2", "current_attempt_id": "formal-1",
            "current": {
                "attempt_id": "formal-1", "status": "solved", "grade": "L2",
                "proof_artifact": {"accepted": True, "target_hash": "target-1",
                                   "proof_hash": "proof-1", "environment_hash": "env-1"},
                "specifications": {"original_to_spec": {"problem_spec_version": 1}},
            },
        }
        artifact = build_presentation(presentation_snapshot(job), "teach")
        formal = [source for source in artifact["sources"] if source.get("scope") == "formal_target"]
        self.assertEqual(1, len(formal))
        self.assertEqual("L2", formal[0]["grade"])
        self.assertEqual("target-1", formal[0]["target_hash"])
        self.assertEqual(1, formal[0]["specification_version"])
        original = next(p for p in artifact["paragraphs"] if p["text"] == "1+1=2")
        self.assertEqual("llm_reviewed", original["grade"])
        self.assertNotIn(formal[0]["id"], original["claim_refs"])
        self.assertEqual("not_verified", artifact["formal_verification"])

    def test_legacy_frozen_policy_keeps_its_original_renderer_and_no_new_delivery(self):
        job = s06.job_fixture()
        job["result"]["presentation_policy_version"] = "faithful-output-v1"
        artifact = build_presentation(presentation_snapshot(job), "teach")
        self.assertEqual("faithful-output-v1", artifact["policy_version"])
        self.assertEqual("deterministic-public-template-v1", artifact["renderer"])
        self.assertNotIn("delivery", artifact)
        self.assertNotIn("output_request", artifact)

    def test_no_eligible_best_effort_candidate_is_incomplete_even_with_old_success_and_answer(self):
        job = evidence_job()
        roots = job["result"]["solver"]["progress"]["root_obligations"]
        roots.update({"covered": 2, "items": [{"ordinal": 1, "status": "satisfied"},
                                              {"ordinal": 2, "status": "satisfied"}]})
        job["result"]["solver"]["best_effort"] = {"status": "no_eligible_candidate",
                                                      "termination_reason": "budget_exhausted"}
        original = copy.deepcopy(job)
        artifact = build_presentation(presentation_snapshot(job), "report")
        self.assertEqual("incomplete", artifact["completion"])
        self.assertEqual([], artifact["delivery"]["verified_claims"])
        self.assertEqual("no_eligible_candidate", artifact["delivery"]["selection"]["status"])
        self.assertEqual(artifact["source_fingerprint"], artifact["delivery"]["source_fingerprint"])
        self.assertEqual(artifact["budget"], artifact["delivery"]["budget"])
        self.assertEqual(original, job)

    def test_selected_candidate_uses_actual_public_projection_field_names(self):
        job = evidence_job()
        roots = job["result"]["solver"]["progress"]["root_obligations"]
        roots.update({"covered": 2, "items": [{"ordinal": 1, "status": "satisfied"},
                                              {"ordinal": 2, "status": "satisfied"}]})
        record = {"candidate_id": "candidate-1", "version": 1, "answer_text": "1+1=2",
                  "answer_completeness": "complete", "selection_eligible": True,
                  "review_state": "whole_reviewed"}
        decision = {"status": "selected", "selected_source_record": record,
                    "excluded_candidate_ids": [], "exclusion_reasons": {}}
        job["result"]["solver"].update(candidate_projection({"state": {
            "candidate_registry": [record], "best_effort_decision": decision}}))
        artifact = build_presentation(presentation_snapshot(job), "report")
        self.assertEqual("complete", artifact["completion"])
        self.assertTrue(artifact["delivery"]["selection"]["eligible"])
        self.assertEqual("complete", artifact["delivery"]["selection"]["completeness"])
        record["answer_completeness"] = "partial"
        job["result"]["solver"].update(candidate_projection({"state": {
            "candidate_registry": [record], "best_effort_decision": decision}}))
        partial = build_presentation(presentation_snapshot(job), "report")
        self.assertEqual("partial", partial["completion"])

    def test_claim_without_current_review_cannot_complete_or_borrow_formal_reference(self):
        job = evidence_job()
        job["result"]["verification"] = {}
        roots = job["result"]["solver"]["progress"]["root_obligations"]
        roots.update({"covered": 2, "items": []})
        artifact = build_presentation(presentation_snapshot(job), "solve")
        self.assertEqual("partial", artifact["completion"])
        self.assertEqual("not_verified", artifact["delivery"]["grade"])
        self.assertEqual([], artifact["delivery"]["verified_claims"])
        self.assertEqual("proposed", artifact["paragraphs"][0]["proof_attempt"]["status"])

    def test_revalidation_revokes_delivery_claims_and_preserves_historical_artifact(self):
        job = evidence_job()
        artifact = build_presentation(presentation_snapshot(job), "teach")
        original = copy.deepcopy(artifact)
        job["result"]["solver"]["state_revision"] += 1
        current = revalidate(artifact, presentation_snapshot(job))
        self.assertEqual("needs_review", current["status"])
        self.assertEqual([], current["delivery"]["verified_claims"])
        self.assertEqual("not_verified", current["delivery"]["grade"])
        self.assertNotEqual("complete", current["completion"])
        self.assertEqual(original, artifact)

    def test_modes_and_failures_have_independent_sealed_artifacts_and_stable_output_requests(self):
        snapshot = presentation_snapshot(evidence_job())
        teach = build_presentation(snapshot, "teach")
        report = build_presentation(snapshot, "report")
        failure = failed_presentation(snapshot, "teach", "presentation_timeout")
        empty = build_presentation(snapshot, "teach", paragraphs=[])
        self.assertNotEqual(teach["output_request"]["id"], report["output_request"]["id"])
        self.assertEqual(teach["output_request"], build_presentation(snapshot, "teach")["output_request"])
        self.assertNotEqual(empty["artifact"], failure["artifact"])
        self.assertEqual(snapshot["answer"], failure["fallback"]["answer"])


class FaithfulF6OutputApiTest(unittest.TestCase):
    def setUp(self):
        self.fixture = s06.PublicPresentationApiTest("test_explicit_outputs_keep_answer_and_persist_artifact")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def test_renderer_timeout_connection_and_style_failure_preserve_original_without_solving(self):
        fixture = self.fixture
        job_id, headers = fixture._job()
        client = fixture.client
        original = client.get(f"/api/agent/jobs/{job_id}").get_json()["result"]
        for error in (TimeoutError("private timeout"), ConnectionError("private disconnect"),
                      ValueError("private style error")):
            with self.subTest(error=type(error).__name__), patch(
                    "showcase.presentation_api.build_presentation", side_effect=error):
                response = client.post(f"/api/agent/jobs/{job_id}/teach", json={}, headers=headers)
                self.assertEqual(200, response.status_code)
                output = response.get_json()["presentation"]
                self.assertEqual("failed", output["status"])
                self.assertEqual(original["final_response"], output["fallback"]["answer"])
                self.assertEqual(0, output["output_request"]["model_calls"])
                self.assertFalse(output["output_request"]["solver_resumed"])
                self.assertNotIn("private", str(output))
        current = client.get(f"/api/agent/jobs/{job_id}").get_json()["result"]
        self.assertEqual(original, current)
