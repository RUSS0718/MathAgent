"""Offline contracts for fixed-candidate APRS ranking."""

import json
import unittest

from ricl_runtime import Candidate, VerifierEvidence, evaluate_fixed_candidates


class FixedCandidateAPRSTests(unittest.TestCase):
    """Check that ranking reacts to verifier evidence, not candidate generation."""

    def test_same_candidates_and_run_context_rank_by_changed_verifier_evidence(self) -> None:
        candidates = (
            Candidate("candidate-b", novelty=1, known_token_cost=20),
            Candidate("candidate-a", novelty=1, known_token_cost=20),
        )
        budget = {"model_requests": {"limit": 2, "used": 1}, "tools": {"limit": 1, "used": 0}}
        capabilities = ("calculator",)
        baseline = evaluate_fixed_candidates(
            candidates,
            (),
            budget_snapshot=budget,
            tool_capabilities=capabilities,
            verifier_capability="offline-integer-addition",
        )
        feedback = evaluate_fixed_candidates(
            candidates,
            (
                VerifierEvidence(
                    candidate_id="candidate-b",
                    evidence_id="evidence-b-1",
                    obligation_id="goal-1",
                    status="accepted",
                    valid=True,
                ),
            ),
            budget_snapshot=budget,
            tool_capabilities=capabilities,
            verifier_capability="offline-integer-addition",
        )

        self.assertEqual(baseline["candidate_ids"], feedback["candidate_ids"])
        self.assertEqual(baseline["candidate_snapshots"], feedback["candidate_snapshots"])
        self.assertEqual(baseline["budget_snapshot"], feedback["budget_snapshot"])
        self.assertEqual(baseline["tool_capabilities"], feedback["tool_capabilities"])
        self.assertEqual(baseline["verifier_capability"], feedback["verifier_capability"])
        self.assertEqual(baseline["priority_order"], ["candidate-a", "candidate-b"])
        self.assertEqual(feedback["priority_order"], ["candidate-b", "candidate-a"])

        event = feedback["trace"][0]
        self.assertEqual(event["candidate_id"], "candidate-b")
        self.assertEqual(event["evidence_ids"], ["evidence-b-1"])
        self.assertEqual(event["verified_obligation_ids"], ["goal-1"])
        self.assertEqual(event["aprs_score"]["verified_gain"], 1)
        self.assertEqual(event["aprs_score"]["evidence_quality"], 1)
        self.assertEqual(event["priority"], 1)
        trace_json = json.dumps(feedback["trace"])
        self.assertNotIn("The answer is 4.", trace_json)
        self.assertNotIn("Compute 2 + 2.", trace_json)
        self.assertNotIn('"answer"', trace_json)
        self.assertNotIn('"prompt"', trace_json)

    def test_gain_counts_only_new_valid_accepted_obligations_not_receipts(self) -> None:
        candidate = Candidate("candidate-a", verified_obligations_at_start=("goal-existing",))
        result = evaluate_fixed_candidates(
            (candidate,),
            (
                VerifierEvidence(
                    "candidate-a", "receipt-1", "goal-receipt", "accepted", True, "tool_receipt"
                ),
                VerifierEvidence("candidate-a", "existing", "goal-existing", "accepted", True),
                VerifierEvidence("candidate-a", "rejected", "goal-rejected", "rejected", True),
                VerifierEvidence("candidate-a", "invalid", "goal-invalid", "accepted", False),
                VerifierEvidence("candidate-a", "new-1", "goal-new", "accepted", True),
                VerifierEvidence("candidate-a", "new-2", "goal-new", "accepted", True),
            ),
            budget_snapshot={"model_requests": {"limit": 1, "used": 1}},
            tool_capabilities=("calculator",),
            verifier_capability="fixture-verifier",
        )

        event = result["trace"][0]
        self.assertEqual(event["verified_obligation_ids"], ["goal-new"])
        self.assertEqual(event["aprs_score"]["verified_gain"], 1)
        self.assertEqual(event["aprs_score"]["evidence_quality"], 1)
        self.assertEqual(
            result["candidate_snapshots"][0]["verified_obligations_at_start"],
            ["goal-existing"],
        )
        self.assertEqual(len(event["verifier_evidence"]), 6)
        receipt = next(
            item for item in event["verifier_evidence"] if item["evidence_id"] == "receipt-1"
        )
        self.assertEqual(receipt["evidence_kind"], "tool_receipt")
        self.assertFalse(receipt["counts_as_verified_gain"])

    def test_disabled_aprs_preserves_search_order_feedback_and_run_context(self) -> None:
        candidates = (Candidate("candidate-z"), Candidate("candidate-a"))
        evidence = (VerifierEvidence("candidate-z", "evidence-z", "goal-1", "accepted", True),)
        budget = {"model_requests": {"limit": 3, "used": 1}}
        enabled = evaluate_fixed_candidates(
            candidates,
            evidence,
            budget_snapshot=budget,
            tool_capabilities=("calculator",),
            verifier_capability="fixture-verifier",
        )
        result = evaluate_fixed_candidates(
            candidates,
            evidence,
            budget_snapshot=budget,
            tool_capabilities=("calculator",),
            verifier_capability="fixture-verifier",
            aprs_enabled=False,
        )

        self.assertFalse(result["ranking_enabled"])
        self.assertEqual(result["candidate_ids"], ["candidate-z", "candidate-a"])
        self.assertEqual(result["priority_order"], ["candidate-z", "candidate-a"])
        self.assertEqual(result["candidate_snapshots"], enabled["candidate_snapshots"])
        self.assertEqual(result["budget_snapshot"], enabled["budget_snapshot"])
        self.assertEqual(result["tool_capabilities"], enabled["tool_capabilities"])
        self.assertEqual(result["verifier_capability"], enabled["verifier_capability"])
        self.assertEqual(
            result["trace"][0]["verifier_evidence"], enabled["trace"][0]["verifier_evidence"]
        )
        self.assertEqual(result["trace"][0]["verifier_evidence"][0]["evidence_id"], "evidence-z")
        self.assertEqual([event["priority"] for event in result["trace"]], [1, 2])
        self.assertTrue(all(event["aprs_score"] is None for event in result["trace"]))

    def test_pareto_front_precedes_dominated_candidates_with_lexicographic_ties(self) -> None:
        candidates = (
            Candidate("dominated", novelty=1, known_token_cost=15),
            Candidate("novel", novelty=4, known_token_cost=5),
            Candidate("cheap", novelty=1, known_token_cost=5),
            Candidate("gain", novelty=2, known_token_cost=10),
        )
        evidence = (
            VerifierEvidence("dominated", "d1", "goal-1", "accepted", True),
            VerifierEvidence("cheap", "c1", "goal-1", "accepted", True),
            VerifierEvidence("gain", "g1", "goal-1", "accepted", True),
        )
        result = evaluate_fixed_candidates(
            candidates,
            evidence,
            budget_snapshot={},
            tool_capabilities=(),
            verifier_capability="fixture-verifier",
        )

        self.assertEqual(result["priority_order"], ["gain", "cheap", "novel", "dominated"])


if __name__ == "__main__":
    unittest.main()
