"""Integrated proof producer and public projection through the actual Job API."""

import json
import unittest

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_star_product_planning import FEATURES
from tests.test_star_product_tools import NEED_PLAN


class FaithfulGraphPublicIntegrationTest(StarJobFixture, unittest.TestCase):
    def run_graph_job(self, enabled):
        """Produce a controller-accepted classified result without a live provider."""
        statement = "PRIVATE_GRAPH_STATEMENT"
        self.open_star([
            NEED_PLAN,
            {"version": 1, "steps": [{"step_id": "private-step", "title": "Base",
                                      "objective": "PRIVATE_GRAPH_SCOPE"}]},
            {"argument": "PRIVATE_GRAPH_PROOF", "claims": [
                {"statement": statement, "label": "hard-verify"}], "blocked": False},
            {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
             "objection": "", "classified_outcomes": [
                 {"category": "Lemma", "statement": statement,
                  "scope": "PRIVATE_GRAPH_SCOPE", "claim_indexes": [0]}]},
            {"final_response": "2"}, ACCEPT,
        ], SHOWCASE_STAR_FEATURES={**FEATURES, **({"proof_graph": True} if enabled else {})},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8))
        job_id = self.create_job()
        self.assertEqual("succeeded", self.terminal(job_id)["status"])
        return job_id

    def test_accepted_producer_reaches_public_report_without_proof_content(self):
        job_id = self.run_graph_job(True)
        graph = self.report(job_id)["solver"]["solver"]["progress"]["proof_graph"]
        self.assertGreater(graph["graph_version"], 0)
        supported = [item for item in graph["propositions"] if item["status"] == "supported"]
        self.assertEqual(1, len(supported), graph)
        accepted = [item for item in graph["attempts"] if item["status"] == "accepted"]
        self.assertEqual(1, len(accepted), graph)
        self.assertEqual(supported[0]["id"], accepted[0]["conclusion"])
        self.assertEqual("llm_reviewed", accepted[0]["grade"])
        self.assertNotIn("PRIVATE_GRAPH", json.dumps(graph))
        self.assertNotIn("private-step", json.dumps(graph))
        calls = len(self.outbound)
        for _ in range(2):
            self.report(job_id)
            self.client.get(f"/api/agent/jobs/{job_id}/events").get_data()
            self.client.get(f"/api/runs/{job_id}/evidence")
        self.assertEqual(calls, len(self.outbound))
        self.assertEqual(graph, self.report(job_id)["solver"]["solver"]["progress"]["proof_graph"])

    def run_dependency_job(self, dependency="S1", *, multiple=False, enabled=True):
        report = {"argument": "proof", "claims": [
            {"statement": "A", "label": "hard-verify"}], "blocked": False}
        review = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                  "objection": "", "classified_outcomes": [
                      {"category": "Lemma", "statement": "A", "scope": "base",
                       "claim_indexes": [0]}]}
        if multiple:
            report["claims"].append({"statement": "C", "label": "hard-verify"})
            review["classified_outcomes"].append(
                {"category": "Lemma", "statement": "C", "scope": "base", "claim_indexes": [1]})
        dependent = {**review, "classified_outcomes": [
            {"category": "Lemma", "statement": "B", "scope": "next",
             "claim_indexes": [0], "dependencies": [dependency]}]}
        self.open_star([
            NEED_PLAN,
            {"version": 1, "steps": [
                {"step_id": "S1", "title": "Base", "objective": "base"},
                {"step_id": "S2", "title": "Next", "objective": "next",
                 "depends_on": ["S1"]}]},
            report, review, {**report, "claims": [{"statement": "B", "label": "hard-verify"}]}, dependent, {"final_response": "2"}, ACCEPT,
        ], SHOWCASE_STAR_FEATURES={**FEATURES, "proof_graph": enabled},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8))
        job_id = self.create_job()
        terminal = self.terminal(job_id)
        return terminal, self.report(job_id)["solver"]["solver"]

    def test_unique_step_dependency_completes(self):
        terminal, result = self.run_dependency_job()
        self.assertEqual("succeeded", terminal["status"], result)
        graph = result["progress"]["proof_graph"]
        self.assertEqual(2, sum(item["status"] == "accepted" for item in graph["attempts"]))
        child = next(item for item in graph["attempts"] if item["dependencies"])
        parent = next(item for item in graph["attempts"] if not item["dependencies"])
        self.assertEqual([parent["conclusion"]], child["dependencies"])

    def test_step_dependency_is_known_protocol_failure_not_job_execution_failure(self):
        terminal, result = self.run_dependency_job(multiple=True)
        self.assertNotEqual("job_execution_failed", terminal.get("error_code"), terminal)
        self.assertEqual("partial_aborted", result["status"])
        self.assertEqual("unsupported_graph_step_dependency", result["result_reason"])
        self.assertEqual([], result["recovery"]["unknown_calls"])
        graph = result["progress"]["proof_graph"]
        self.assertEqual(2, sum(item["status"] == "accepted" for item in graph["attempts"]))

    def test_exact_result_dependency_completes(self):
        terminal, result = self.run_dependency_job("S1:outcome-1")
        self.assertEqual("succeeded", terminal["status"], result)
        self.assertEqual(2, sum(item["status"] == "accepted"
                               for item in result["progress"]["proof_graph"]["attempts"]))

    def test_legacy_step_dependency_completes(self):
        terminal, result = self.run_dependency_job(enabled=False)
        self.assertEqual("succeeded", terminal["status"], result)
        self.assertNotIn("proof_graph", result["progress"])

    def test_default_job_does_not_add_graph_projection(self):
        job_id = self.run_graph_job(False)
        self.assertNotIn("proof_graph", self.report(job_id)["solver"]["solver"]["progress"])
