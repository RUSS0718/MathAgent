"""Controlled public Job regression for the original D admission failure.

New rulings are explicitly controlled; none represent a natural solve.
The unchanged captured D replay remains in ignored diagnostic artifacts.
"""

import unittest

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_star_product_planning import FEATURES
from tests.test_star_product_tools import NEED_PLAN


class DependencySource189DiagnosticTest(StarJobFixture, unittest.TestCase):
    def run_case(self, replacement, *, budget=9, enabled=True, dependency=True, repair=False,
                 parent_review=None, include_replacement=True):
        report = {"argument": "controlled proof", "claims": [
            {"statement": "parent result", "label": "hard-verify"}], "blocked": False}
        accept = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                  "objection": ""}
        self.open_star([
            NEED_PLAN,
            {"version": 1, "steps": [
                {"step_id": "S1", "title": "Parent", "objective": "parent"},
                {"step_id": "S2", "title": "Child", "objective": "child",
                 "depends_on": ["S1"] if dependency else []}]},
            report,
            parent_review if parent_review is not None else {**accept, "classified_outcomes": [
                {"category": "Answer", "statement": "parent result", "scope": "parent",
                 "claim_indexes": [0], "receipt_ids": ["unavailable-receipt"]}]},
            *([replacement] if enabled and dependency and include_replacement else []),
            *([{"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": "",
                "classified_outcomes": [{"category": "Lemma", "statement": "parent result",
                    "scope": "parent", "claim_indexes": [0]}]}] if repair else []),
            {**report, "claims": [{"statement": "child result", "label": "hard-verify"}]},
            {**accept, "classified_outcomes": [
                {"category": "Answer", "statement": "child result", "scope": "child",
                 "claim_indexes": [0], "dependencies": ["S1"] if dependency else []}]},
            {"final_response": "complete controlled answer"}, ACCEPT,
        ], SHOWCASE_STAR_FEATURES={**FEATURES, "proof_graph": enabled},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=budget, max_http_attempts=budget))
        job_id = self.create_job()
        terminal = self.terminal(job_id)
        result = self.report(job_id)["solver"]["solver"]
        return job_id, terminal, result

    def test_rejected_parent_classification_cannot_back_successor_answer(self):
        job_id, terminal, result = self.run_case({
            "goal_gate": "NO", "logic_gate": "FAIL", "verdict": "CHALLENGE", "objection": "unsupported"})
        self.assertNotEqual("succeeded", terminal["status"])
        self.assertEqual("dependency_reclassification_failed", result["result_reason"])
        self.assertEqual([], result["recovery"]["unknown_calls"])
        graph = result["progress"]["proof_graph"]
        self.assertFalse(any(row["status"] == "accepted" for row in graph["attempts"]))
        self.assertEqual(5, len(self.outbound))
        for _ in range(2):
            self.report(job_id)
        self.assertEqual(5, len(self.outbound))

    def test_new_independent_ruling_promotes_parent_and_child_consumes_it(self):
        def independent(request):
            self.assertTrue(request["reclassification_of"])
            self.assertEqual("unverified_tool_receipt", request["admission_rejections"][0]["reason"])
            return {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": "",
                    "classified_outcomes": [{"category": "Lemma", "statement": "parent result",
                        "scope": "parent", "claim_indexes": [0], "receipt_ids": []}]}
        job_id, terminal, result = self.run_case(independent)
        self.assertEqual("succeeded", terminal["status"], result)
        self.assertEqual(9, len(self.outbound))
        graph = result["progress"]["proof_graph"]
        self.assertEqual(2, sum(r["status"] == "accepted" for r in graph["attempts"]))
        parent = next(r for r in graph["attempts"] if r["status"] == "accepted" and not r["dependencies"])
        child = next(r for r in graph["attempts"] if r["dependencies"])
        self.assertEqual([parent["conclusion"]], child["dependencies"])
        self.assertEqual("accepted", self.report(job_id)["semantics"]["whole_review"])
        job = self.job(job_id)
        attempts = job["result"]["request_attempts"]
        self.assertEqual(9, len({a["attempt_id"] for a in attempts}))
        self.assertEqual(9, job["result"]["budget"]["logical_calls"])
        self.assertNotEqual(attempts[3]["solver_call_id"], attempts[4]["solver_call_id"])

    def test_root_budget_prevents_reclassification_dispatch(self):
        _, terminal, _ = self.run_case({}, budget=4)
        self.assertNotEqual("succeeded", terminal["status"])
        self.assertEqual(4, len(self.outbound))

    def test_unknown_reclassification_is_not_automatically_reissued(self):
        job_id, terminal, result = self.run_case(TimeoutError("controlled unknown"))
        self.assertNotEqual("succeeded", terminal["status"])
        self.assertEqual(1, len(result["recovery"]["unknown_calls"]))
        self.assertNotEqual("job_execution_failed", terminal.get("error"))
        for _ in range(2):
            self.report(job_id)
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers())
        self.assertEqual(409, response.status_code)
        self.assertEqual(5, len(self.outbound))

    def test_repeated_invalid_classification_stops_at_parent(self):
        _, terminal, result = self.run_case({
            "goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": "",
            "classified_outcomes": [{"category": "Answer", "statement": "parent result",
                "scope": "parent", "claim_indexes": [0], "receipt_ids": ["unavailable-receipt"]}]})
        self.assertNotEqual("succeeded", terminal["status"])
        self.assertEqual("dependency_reclassification_failed", result["result_reason"])
        self.assertEqual(5, len(self.outbound))

    def test_conjecture_does_not_satisfy_required_premise(self):
        _, terminal, result = self.run_case({
            "goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": "",
            "classified_outcomes": [{"category": "Conjecture", "statement": "parent result",
                "scope": "parent", "claim_indexes": [0]}]})
        self.assertNotEqual("succeeded", terminal["status"])
        self.assertEqual("dependency_reclassification_failed", result["result_reason"])
        self.assertEqual(5, len(self.outbound))

    def test_non_graph_mode_does_not_add_a_ruling(self):
        _, terminal, _ = self.run_case({}, enabled=False)
        self.assertEqual("succeeded", terminal["status"])
        self.assertEqual(8, len(self.outbound))

    def test_no_dependent_successor_does_not_add_a_ruling(self):
        _, terminal, _ = self.run_case({}, dependency=False)
        self.assertEqual("succeeded", terminal["status"])
        self.assertEqual(8, len(self.outbound))

    def test_known_format_repair_has_separate_explicit_lineage(self):
        from tests.star_product_support import RawProviderContent

        _, terminal, _ = self.run_case(RawProviderContent("{bad-json"), repair=True, budget=10)
        self.assertEqual("succeeded", terminal["status"])
        self.assertEqual(10, len(self.outbound))
        semantic, formatted = self.outbound[4:6]
        self.assertEqual(semantic["call_id"] + ":repair-1", formatted["call_id"])
        self.assertEqual(semantic["reclassification_of"], formatted["reclassification_of"])

    def test_new_computation_without_usable_receipt_never_becomes_a_premise(self):
        _, terminal, result = self.run_case({
            "goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": "",
            "classified_outcomes": [{"category": "Computation", "statement": "parent result",
                "scope": "finite candidates only", "claim_indexes": [0], "receipt_ids": []}]})
        self.assertNotEqual("succeeded", terminal["status"])
        self.assertEqual("dependency_reclassification_failed", result["result_reason"])
        self.assertEqual(5, len(self.outbound))

    def test_one_legal_result_and_rejected_extra_do_not_add_a_call(self):
        _, terminal, _ = self.run_case({}, include_replacement=False, parent_review={
            "goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": "",
            "classified_outcomes": [
                {"category": "Lemma", "statement": "parent result", "scope": "parent", "claim_indexes": [0]},
                {"category": "Computation", "statement": "extra", "scope": "finite only", "claim_indexes": [0]}]})
        self.assertEqual("succeeded", terminal["status"])
        self.assertEqual(8, len(self.outbound))

    def test_original_unknown_review_does_not_trigger_semantic_reclassification(self):
        _, terminal, result = self.run_case({}, parent_review=TimeoutError("original unknown"))
        self.assertNotEqual("succeeded", terminal["status"])
        self.assertEqual(1, len(result["recovery"]["unknown_calls"]))
        self.assertEqual(4, len(self.outbound))
        self.assertFalse(any("reclassification_of" in r for r in self.outbound))

    def test_new_ruling_with_bad_claim_target_does_not_start_another_review(self):
        self.assert_incomplete_ruling_stops(claim_index=9, both_directions_proved=True)

    def test_new_ruling_with_missing_direction_does_not_start_counterexample_search(self):
        self.assert_incomplete_ruling_stops(claim_index=0, both_directions_proved=False)

    def assert_incomplete_ruling_stops(self, *, claim_index, both_directions_proved):
        _, terminal, result = self.run_case({
            "goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": "",
            "answer_claim": {"claim_index": claim_index,
                "both_directions_proved": both_directions_proved,
                "assumptions": [], "approach": "incomplete controlled argument"},
            "classified_outcomes": [{"category": "Lemma", "statement": "parent result",
                "scope": "parent", "claim_indexes": [0]}]})
        self.assertNotEqual("succeeded", terminal["status"])
        self.assertEqual("dependency_reclassification_failed", result["result_reason"])
        self.assertEqual(5, len(self.outbound))
