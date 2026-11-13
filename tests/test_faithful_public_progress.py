"""Public progress distinguishes historical reviews from current eligibility."""

import unittest
from copy import deepcopy

from showcase.final_evidence import artifact_identity
from showcase.star_product_summary import progress_summary


def reviewed_state():
    fact = {"result_id": "f", "source": "s", "statement": "1+1=2",
            "valid": True, "proven": True, "category": "Lemma",
            "evidence_level": "llm_reviewed", "dependencies": [], "claim_indexes": [0]}
    return {
        "run_id": "r", "plan_version": 1, "attempt_index": 0, "specification_version": 1,
        "problem_intake": {"version": "auto-problem-spec-v1"},
        "plan": {"steps": [{"step_id": "s"}, {"step_id": "t", "depends_on": ["s"]}]},
        "steps": {key: {"verification": {"valid": True, "verdict": "ACCEPT"}}
                  for key in ("s", "t")},
        "accepted_results": [fact], "verified_results_ledger": [fact],
        "obligation_ledger": [{"obligation_id": "root", "status": "satisfied",
                               "evidence_refs": ["e"]}],
        "obligation_evidence_ledger": [{"evidence_id": "e", "valid": True,
            "source": "s", "result_id": "f", "specification_version": 1, "claim_indexes": [0]}],
        "final_solution_attempts": [{"candidate": "2", "review": {"verdict": "ACCEPT"},
            "plan_version": 1, "attempt_index": 0, "specification_version": 1,
            "accepted_results": [deepcopy(fact)]}],
        "whole_solution_reviews": [{"verdict": "ACCEPT", "artifact": artifact_identity("2"),
            "source": {"run_id": "r", "call_id": "review", "candidate_version": 1,
                       "plan_version": 1, "attempt_index": 0, "specification_version": 1}}],
        "calls": {"review": {"role": "whole_solution_verifier", "run_id": "r",
            "status": "completed", "request": {"solution_candidate": "2"},
            "response": {"verdict": "ACCEPT"}}},
        "proof_graph": {"current_version": 1, "snapshots": [{"graph_version": 1,
            "attempts": {"a": {"result_id": "f", "status": "accepted", "conclusion": "p"}},
            "propositions": {"p": {"status": "supported", "conflict": False}}}]},
    }


def rescued_state():
    state = reviewed_state()
    rescued = {**state["verified_results_ledger"][0], "result_id": "rescued",
               "source": "old-step", "plan_version": 0, "attempt_index": 0,
               "review_call_id": "old-review"}
    state["calls"]["old-review"] = {"plan_version": 0, "attempt_index": 0}
    state["accepted_results"].append(rescued)
    state["verified_results_ledger"].append(rescued)
    state["rescued_results"] = [rescued]
    state["final_solution_attempts"][0]["accepted_results"].append(deepcopy(rescued))
    graph = state["proof_graph"]["snapshots"][0]
    graph["attempts"]["rescued"] = {"result_id": "rescued", "status": "accepted",
                                    "conclusion": "rescued-proposition"}
    graph["propositions"]["rescued-proposition"] = {"status": "supported", "conflict": False}
    return state


class FaithfulPublicProgressTest(unittest.TestCase):
    def test_authorized_older_rescue_remains_eligible_as_current_candidate_dependency(self):
        partial = progress_summary(rescued_state())["partial"]
        self.assertTrue(partial["candidates"][0]["eligible"])
        self.assertEqual([], partial["unresolved"])

    def test_invalidated_or_graph_conflicted_rescue_cannot_support_candidate(self):
        for invalidation in ("record", "graph"):
            with self.subTest(invalidation=invalidation):
                state = rescued_state()
                if invalidation == "record":
                    state["rescued_results"][0]["invalidated"] = True
                else:
                    state["proof_graph"]["snapshots"][0]["propositions"][
                        "rescued-proposition"]["conflict"] = True
                partial = progress_summary(state)["partial"]
                self.assertFalse(partial["candidates"][0]["eligible"])
                self.assertIn("whole_solution_review", partial["unresolved"])

    def test_unused_conjecture_and_old_classifications_do_not_veto_current_work(self):
        for history in (
            {"category": "Conjecture", "proven": False, "evidence_level": "conjecture"},
            {"plan_version": 0, "invalidated": True},
            {"attempt_index": -1, "invalidated": True},
            {"specification_version": 0, "invalidated": True},
            {"review_call_id": "old-review", "invalidated": True},
        ):
            with self.subTest(history=history):
                state = reviewed_state()
                state["calls"]["old-review"] = {"plan_version": 0, "attempt_index": 0}
                old = {**state["verified_results_ledger"][0], "result_id": "old", **history}
                state["verified_results_ledger"].append(old)
                partial = progress_summary(state)["partial"]
                self.assertEqual(["步骤 1", "步骤 2"], partial["accepted_steps"])
                self.assertTrue(partial["candidates"][0]["eligible"])
                self.assertEqual([], partial["unresolved"])

    def test_skipped_optional_work_does_not_veto_bound_complete_candidate(self):
        state = reviewed_state()
        state["plan"]["steps"].append({"step_id": "optional", "auxiliary_goal_ids": ["aux"]})
        state["steps"]["optional"] = {"status": "SKIPPED"}
        partial = progress_summary(state)["partial"]
        self.assertEqual(["步骤 1", "步骤 2"], partial["accepted_steps"])
        self.assertTrue(partial["candidates"][0]["eligible"])
        self.assertEqual([], partial["unresolved"])

    def test_skipped_work_does_not_bypass_required_obligations_or_candidate_dependencies(self):
        for missing in ("root", "candidate_dependency"):
            with self.subTest(missing=missing):
                state = reviewed_state()
                state["plan"]["steps"].append({"step_id": "optional"})
                state["steps"]["optional"] = {"status": "SKIPPED"}
                if missing == "root":
                    state["obligation_ledger"][0]["status"] = "open"
                else:
                    old = {**state["verified_results_ledger"][0], "result_id": "old",
                           "plan_version": 0, "invalidated": True}
                    state["verified_results_ledger"].append(old)
                    state["final_solution_attempts"][0]["accepted_results"].append(deepcopy(old))
                partial = progress_summary(state)["partial"]
                self.assertFalse(partial["candidates"][0]["eligible"])
                self.assertIn("whole_solution_review", partial["unresolved"])

    def test_dependency_conflict_removes_current_credit_but_retains_historical_review(self):
        state = reviewed_state()
        self.assertTrue(progress_summary(state)["partial"]["candidates"][0]["eligible"])
        state["proof_graph"]["snapshots"][0]["propositions"]["p"]["conflict"] = True
        partial = progress_summary(state)["partial"]
        self.assertEqual([], partial["accepted_steps"])
        self.assertFalse(partial["candidates"][0]["eligible"])
        self.assertEqual("ACCEPT", partial["candidates"][0]["review"])
        self.assertIn("whole_solution_review", partial["unresolved"])
        self.assertIn("义务 1", partial["unresolved"])

    def test_invalidated_fact_excludes_dependent_steps_and_candidate(self):
        state = reviewed_state()
        state["verified_results_ledger"][0]["invalidated"] = True
        partial = progress_summary(state)["partial"]
        self.assertEqual([], partial["accepted_steps"])
        self.assertFalse(partial["candidates"][0]["eligible"])

    def test_candidate_requires_audited_review_binding(self):
        state = reviewed_state()
        state["calls"]["review"]["request"]["solution_candidate"] = "other"
        partial = progress_summary(state)["partial"]
        self.assertFalse(partial["candidates"][0]["eligible"])
        self.assertIn("whole_solution_review", partial["unresolved"])

    def test_candidate_sensitive_multiword_value_is_suppressed(self):
        state = reviewed_state()
        state["final_solution_attempts"][0]["candidate"] = "full_prompt=[redacted] private suffix"
        text = progress_summary(state)["partial"]["candidates"][0]["answer_text"]
        self.assertNotIn("private suffix", text)
