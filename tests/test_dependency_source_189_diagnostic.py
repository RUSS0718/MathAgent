"""Controlled public Job regression for the original D admission failure.

This characterizes the failure, not a successful repair or natural solve.
The unchanged captured D replay remains in ignored diagnostic artifacts.
"""

import unittest

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import StarJobFixture
from tests.test_star_product_planning import FEATURES
from tests.test_star_product_tools import NEED_PLAN


class DependencySource189DiagnosticTest(StarJobFixture, unittest.TestCase):
    def test_rejected_parent_classification_cannot_back_successor_answer(self):
        report = {"argument": "controlled proof", "claims": [
            {"statement": "parent result", "label": "hard-verify"}], "blocked": False}
        accept = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                  "objection": ""}
        self.open_star([
            NEED_PLAN,
            {"version": 1, "steps": [
                {"step_id": "S1", "title": "Parent", "objective": "parent"},
                {"step_id": "S2", "title": "Child", "objective": "child",
                 "depends_on": ["S1"]}]},
            report,
            {**accept, "classified_outcomes": [
                {"category": "Answer", "statement": "parent result", "scope": "parent",
                 "claim_indexes": [0], "receipt_ids": ["unavailable-receipt"]}]},
            {**report, "claims": [{"statement": "child result", "label": "hard-verify"}]},
            {**accept, "classified_outcomes": [
                {"category": "Answer", "statement": "child result", "scope": "child",
                 "claim_indexes": [0], "dependencies": ["S1"]}]},
        ], SHOWCASE_STAR_FEATURES={**FEATURES, "proof_graph": True},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8))
        job_id = self.create_job()
        terminal = self.terminal(job_id)
        result = self.report(job_id)["solver"]["solver"]
        self.assertNotEqual("succeeded", terminal["status"])
        self.assertEqual("unsupported_graph_step_dependency", result["result_reason"])
        self.assertEqual([], result["recovery"]["unknown_calls"])
        graph = result["progress"]["proof_graph"]
        self.assertFalse(any(row["status"] == "accepted" for row in graph["attempts"]))
        self.assertEqual(6, len(self.outbound))
        for _ in range(2):
            self.report(job_id)
        self.assertEqual(6, len(self.outbound))
