"""Final proof delivery observed through the authenticated public STAR Job.

ALIGN-AC-10/11: the final generator and the whole-solution verifier must
actually receive the complete proof bodies of still-valid accepted steps,
their classified outcomes and their real computation receipts, while dead
(archived, invalidated) derivations stay absent. Markers embedded in the
proof bodies distinguish valid from invalidated reports without asserting
internal bookkeeping.
"""

import json
import unittest

from showcase.final_evidence import artifact_identity
from showcase.run_budget import RunBudgetLimits
from showcase.tools import ToolRegistry
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_star_product_planning import FEATURES
from tests.test_star_product_tools import NEED_PLAN, VERDICT

TOOLS_FEATURES = {**FEATURES, "local_code_tool": True}

VALID_STEP_1 = "PROOF-MARKER-VALID-S1-derivation of the addition identity"
DEAD_STEP_2 = "PROOF-MARKER-DEAD-S2-archived wrong boundary argument"
VALID_STEP_2 = "PROOF-MARKER-VALID-S2-corrected boundary argument"

PLAN = {"version": 1, "steps": [
    {"step_id": "s1", "title": "Add", "objective": "Compute 1+1"},
    {"step_id": "s2", "title": "Bound", "objective": "Bound the sum", "depends_on": ["s1"]},
]}
ONE_STEP = {"version": 1, "steps": [{"step_id": "s1", "title": "Add", "objective": "Compute 1+1"}]}

TRACE_BACK_TO_S2 = {
    "goal_gate": "PARTIAL", "logic_gate": "FAIL", "verdict": "TRACE_BACK",
    "objection": "the boundary argument is wrong", "trace_back_to": 2,
}


def step(argument, claims=()):
    return {"argument": argument, "claims": list(claims), "blocked": False}


class StarFinalProofTest(StarJobFixture, unittest.TestCase):
    def run_star(self, replies, **config):
        features = {**FEATURES, **config.pop("SHOWCASE_STAR_FEATURES", {})}
        self.open_star(replies, SHOWCASE_STAR_FEATURES=features,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                           max_model_calls=20, max_http_attempts=20), **config)
        job_id = self.create_job()
        job = self.terminal(job_id)
        return job_id, job

    def test_valid_proof_bodies_reach_final_generation_and_whole_review(self):
        """AC-10: complete valid reports enter the actual requests; dead ones don't."""
        job_id, job = self.run_star([
            NEED_PLAN, PLAN,
            step(VALID_STEP_1), VERDICT,
            step(DEAD_STEP_2), TRACE_BACK_TO_S2,
            step(VALID_STEP_2), VERDICT,
            {"final_response": "1+1=2, bounded as required"}, ACCEPT,
        ])
        self.assertEqual("succeeded", job["status"], job)
        final = next(r for r in self.outbound if r["role"] == "final_generator")
        review = next(r for r in self.outbound if r["role"] == "whole_solution_verifier")
        payload = json.dumps(final, ensure_ascii=False)
        # The verifier saw the full proof bodies; the final generator request
        # must contain the still-valid ones and never the archived derivation.
        self.assertIn(VALID_STEP_1, payload)
        self.assertIn(VALID_STEP_2, payload)
        self.assertNotIn(DEAD_STEP_2, payload)
        proofs = final["step_proofs"]
        self.assertEqual(["s1", "s2"], [proof["step_id"] for proof in proofs])
        self.assertEqual([VALID_STEP_1, VALID_STEP_2],
                         [proof["argument"] for proof in proofs])
        # The whole-solution verifier receives the actual candidate and the
        # same legal basis, so it can check the candidate against the proofs.
        self.assertIn(VALID_STEP_1, json.dumps(review, ensure_ascii=False))
        self.assertEqual(final["step_proofs"], review["step_proofs"])
        self.assertEqual("1+1=2, bounded as required", review["solution_candidate"])
        # Each proof carries the controller-recorded review ruling of its step.
        self.assertEqual(["ACCEPT"] * 2, [proof["review"]["verdict"] for proof in proofs])
        self.assertEqual(["YES"] * 2, [proof["review"]["goal_gate"] for proof in proofs])
        # Original artifact identities resolve against the persisted reports.
        for proof in proofs:
            self.assertEqual(artifact_identity(proof["argument"]), proof["artifact"])
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        bound = [item for item in evidence["verification"]["history"]
                 if item["artifact"] == artifact_identity("1+1=2, bounded as required")][-1]
        self.assertEqual([{"step_ordinal": 1, "argument": artifact_identity(VALID_STEP_1),
                           "receipt_ids": []},
                          {"step_ordinal": 2, "argument": artifact_identity(VALID_STEP_2),
                           "receipt_ids": []}],
                         bound["proof_sources"])

    def test_computation_receipts_and_scope_reach_the_delivered_basis(self):
        """AC-10: applicable code/input/output and the finite scope travel with the proof."""
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda args: 2)
        claim = {
            "statement": "1+1=2 by direct computation",
            "label": "easy-verify",
            "tool_request": {"tool": "polynomial_check", "arguments": {"expression": "1+1"},
                             "scope": "finite_computation", "expected_output": 2},
        }
        job_id, job = self.run_star([
            NEED_PLAN, ONE_STEP, step(VALID_STEP_1, [claim]), VERDICT,
            {"final_response": "1+1=2"}, ACCEPT,
        ], SHOWCASE_STAR_FEATURES=TOOLS_FEATURES, SHOWCASE_STAR_REGISTRY=registry)
        self.assertEqual("succeeded", job["status"], job)
        final = next(r for r in self.outbound if r["role"] == "final_generator")
        proof = final["step_proofs"][0]
        receipts = proof["tool_receipts"]
        self.assertEqual(1, len(receipts), proof)
        receipt = receipts[0]
        self.assertTrue(receipt["executed"])
        self.assertEqual("success", receipt["status"])
        self.assertEqual({"expression": "1+1"}, receipt["input"])
        self.assertEqual(2, receipt["output"])
        claim = proof["claims"][0]
        self.assertEqual("verified", claim["label"])
        self.assertEqual("finite_computation", claim["verification_scope"])
        review = next(r for r in self.outbound if r["role"] == "whole_solution_verifier")
        self.assertEqual(final["step_proofs"], review["step_proofs"])

    def test_classified_outcomes_deliver_and_conjectures_stay_out_of_the_basis(self):
        """AC-10/AC-03 of #77 continues: proven classifications travel, conjectures don't."""
        lemma = "LEMMA-MARKER-boundary term vanishes on the unit circle"
        conjecture = "CONJECTURE-MARKER-the equality case extends to all radii"
        challenge = {
            "goal_gate": "PARTIAL", "logic_gate": "UNCERTAIN", "verdict": "CHALLENGE",
            "objection": "prove the boundary term first",
            "classified_outcomes": [
                {"category": "Lemma", "statement": lemma, "scope": "unit circle",
                 "claim_indexes": [0], "receipt_ids": [], "dependencies": ["s1"]},
                {"category": "Conjecture", "statement": conjecture, "scope": "all radii",
                 "claim_indexes": [], "receipt_ids": [], "dependencies": []},
            ],
        }
        job_id, job = self.run_star([
            NEED_PLAN, PLAN,
            step(VALID_STEP_1), VERDICT,
            step(VALID_STEP_2, [{"statement": "boundary term vanishes on the circle",
                                 "label": "hard-verify"}]), challenge,
            step("boundary term handled in round one"), VERDICT,
            {"final_response": "bounded"}, ACCEPT,
        ])
        self.assertEqual("succeeded", job["status"], job)
        final = next(r for r in self.outbound if r["role"] == "final_generator")
        statements = [fact.get("statement") for fact in final["accepted_results"]]
        self.assertIn(lemma, statements)
        payload = json.dumps(final, ensure_ascii=False)
        self.assertNotIn(conjecture, payload)
        # The accepted s2 derivation is the round-one report; the challenged
        # round-zero derivation stays visible only through the challenge history.
        self.assertIn("boundary term handled in round one", payload)
        self.assertEqual("s2", final["step_proofs"][1]["step_id"])
        self.assertEqual("boundary term handled in round one",
                         final["step_proofs"][1]["argument"])
        self.assertEqual(1, len(final["step_proofs"][1]["challenge_history"]))
        review = next(r for r in self.outbound if r["role"] == "whole_solution_verifier")
        self.assertIn(lemma, json.dumps(review, ensure_ascii=False))
        self.assertNotIn(conjecture, json.dumps(review, ensure_ascii=False))

    def test_rewrite_retry_keeps_proof_basis_and_binds_only_the_delivered_text(self):
        """AC-11: a rewritten candidate is re-reviewed with the same basis; old review cannot bind."""
        reject = {"verdict": "REJECT", "reason": "the bound is missing"}
        job_id, job = self.run_star([
            NEED_PLAN, ONE_STEP, step(VALID_STEP_1), VERDICT,
            {"final_response": "draft without a bound"}, reject,
            {"final_response": "bounded final answer"}, ACCEPT,
        ])
        self.assertEqual("succeeded", job["status"], job)
        generators = [r for r in self.outbound if r["role"] == "final_generator"]
        self.assertEqual(2, len(generators))
        for request in generators:
            self.assertEqual(["s1"], [proof["step_id"] for proof in request["step_proofs"]])
            self.assertIn(VALID_STEP_1, request["step_proofs"][0]["argument"])
        self.assertEqual("the bound is missing",
                         generators[1]["previous_review"]["reason"])
        check = self.report(job_id)["checks"]
        self.assertEqual([artifact_identity("draft without a bound"),
                          artifact_identity("bounded final answer")],
                         [item["artifact"] for item in check["history"]])
        self.assertEqual("same_artifact", check["binding"])
        # An LLM acceptance is never displayed as a formal proof.
        self.assertEqual("needs_review", check["acceptance"])
        self.assertEqual("unknown", check["status"])
        delivered = check["history"][-1]
        self.assertEqual(artifact_identity("bounded final answer"), delivered["artifact"])
        self.assertEqual([{"step_ordinal": 1, "argument": artifact_identity(VALID_STEP_1),
                           "receipt_ids": []}],
                         delivered["proof_sources"])

    def test_unavailable_whole_review_stays_unverified_without_forged_acceptance(self):
        """AC-10: an unfulfillable review branch keeps the candidate unverified."""
        stuck_request = {"verdict": "REJECT", "reason": "I need a computation first",
                         "tool_request": {"tool": "polynomial_check", "arguments": {"q": 1},
                                          "scope": "finite_computation"}}
        job_id, job = self.run_star([
            NEED_PLAN, ONE_STEP, step(VALID_STEP_1), VERDICT,
            {"final_response": "bounded"}, stuck_request, stuck_request,
        ])
        self.assertEqual("failed", job["status"], job)
        self.assertEqual("completed_unverified", job["result"]["solver"]["status"])
        final = next(r for r in self.outbound if r["role"] == "final_generator")
        self.assertEqual(["s1"], [proof["step_id"] for proof in final["step_proofs"]])
        self.assertNotEqual("completed_llm_reviewed", job["result"]["solver"]["status"])
