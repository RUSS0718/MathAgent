"""Controlled public Job regression for the original D admission failure.

New rulings are explicitly controlled; none represent a natural solve.
The unchanged captured D replay remains in ignored diagnostic artifacts.
"""

import unittest
import uuid

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_star_product_planning import FEATURES
from tests.test_star_product_tools import NEED_PLAN


class DependencySource189DiagnosticTest(StarJobFixture, unittest.TestCase):
    def test_unknown_reclassification_explicit_retry_keeps_identity_and_budget(self):
        job_id, terminal, result = self.run_case(TimeoutError("controlled unknown"), budget=10)
        old_id = result["recovery"]["unknown_calls"][0]["call_id"]
        old_budget = terminal["result"]["budget"]
        original = self.outbound[4]
        for decision in ({}, {"retry_call": {"call_id": "unrelated", "new_call_id": str(uuid.uuid4())}},
                         {"retry_call": {"call_id": old_id, "new_call_id": old_id}}):
            response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json=decision,
                                        headers=self.headers())
            self.assertEqual(409, response.status_code)
        self.assertEqual(5, len(self.outbound))

        new_id = str(uuid.uuid4())
        self.replies.insert(0, {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
            "objection": "", "classified_outcomes": [{"category": "Lemma", "statement": "parent result",
                "scope": "parent", "claim_indexes": [0]}]})
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={"retry_call": {
            "call_id": old_id, "new_call_id": new_id}}, headers=self.headers())
        self.assertEqual(202, response.status_code)
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual(10, len(self.outbound))
        retried = self.outbound[5]
        self.assertEqual(new_id, retried["call_id"])
        for key in ("report", "step", "checkpoint", "specification_version", "reclassification_of"):
            self.assertEqual(original.get(key), retried.get(key), key)
        self.assertEqual(2, sum("reclassification_of" in row for row in self.outbound))
        budget = final["result"]["budget"]
        self.assertEqual(old_budget["deadline_at"], budget["deadline_at"])
        self.assertEqual(old_budget["reserved_tokens"], budget["reserved_tokens"])
        self.assertEqual(1, budget["unknown_attempts"])
        self.assertEqual(10, budget["http_attempts"])
        self.assertEqual(10, budget["logical_calls"])
        recovery = self.report(job_id)["solver"]["solver"]["recovery"]
        self.assertEqual([], recovery["unknown_calls"])
        self.assertEqual(1, len(recovery["retries"]))
        self.assertEqual(old_id, recovery["retries"][0]["retry_of"])
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertEqual(1, sum(row.get("solver_event_type") == "dependency_review_reserved"
                                for row in evidence["timeline"]))

    def test_second_unknown_needs_new_decision_and_retried_challenge_stops(self):
        job_id, first, result = self.run_case(TimeoutError("first unknown"), budget=12)
        original_budget = first["result"]["budget"]
        original = self.outbound[4]
        replies = [TimeoutError("second unknown"), {
            "goal_gate": "PARTIAL", "logic_gate": "UNCERTAIN", "verdict": "CHALLENGE",
            "objection": "Only a local lemma",
            "classified_outcomes": [{"category": "Lemma", "statement": "parent result",
                "scope": "parent", "claim_indexes": [0]}]}]
        for index, reply in enumerate(replies):
            self.replies.insert(0, reply)
            old_id = result["recovery"]["unknown_calls"][0]["call_id"]
            ordinary = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers())
            self.assertEqual(409, ordinary.status_code)
            self.assertEqual(5 + index, len(self.outbound))
            response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={"retry_call": {
                "call_id": old_id, "new_call_id": str(uuid.uuid4())}}, headers=self.headers())
            self.assertEqual(202, response.status_code)
            final = self.terminal(job_id)
            result = self.report(job_id)["solver"]["solver"]
            self.assertEqual("failed", final["status"])
        self.assertEqual(7, len(self.outbound))
        self.assertTrue(all(row["role"] == "step_verifier" for row in self.outbound[3:]))
        self.assertEqual("dependency_reclassification_failed", result["result_reason"])
        self.assertEqual(2, len(result["recovery"]["retries"]))
        self.assertEqual([], result["recovery"]["unknown_calls"])
        self.assertEqual(2, final["result"]["budget"]["unknown_attempts"])
        self.assertEqual(original_budget["deadline_at"], final["result"]["budget"]["deadline_at"])
        for retry in self.outbound[5:]:
            for key in ("report", "step", "checkpoint", "specification_version", "reclassification_of"):
                self.assertEqual(original.get(key), retry.get(key), key)
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertEqual(1, sum(row.get("solver_event_type") == "dependency_review_reserved"
                                for row in evidence["timeline"]))

    def test_new_challenge_with_legal_partial_lemma_stops_without_more_search(self):
        job_id, terminal, result = self.run_case({
            "goal_gate": "PARTIAL", "logic_gate": "UNCERTAIN", "verdict": "CHALLENGE",
            "objection": "Only a local lemma is proved",
            "classified_outcomes": [{"category": "Lemma", "statement": "parent result",
                "scope": "parent", "claim_indexes": [0]}]})
        self.assertEqual("failed", terminal["status"])
        self.assertEqual("dependency_reclassification_failed", result["result_reason"])
        self.assertEqual(["explore", "planner", "reasoner", "step_verifier", "step_verifier"],
                         [request["role"] for request in self.outbound])
        for _ in range(2):
            self.report(job_id)
            response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers())
            self.assertEqual(409, response.status_code)
        self.assertEqual(5, len(self.outbound))

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
