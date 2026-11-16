"""Natural-input guidance observed at public Job and provider HTTP boundaries."""

import os
import unittest
from copy import deepcopy
from unittest.mock import patch

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, SOLVED, StarJobFixture
from tests.test_faithful_s03_job import CAPACITY_POLICY, ENDPOINT, SPEC


class NaturalIntakeJobTest(StarJobFixture, unittest.TestCase):
    def open_intake(self, replies):
        """Use the frozen dependency policy with only the provider HTTP scripted."""
        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        self.open_star(replies,
            SHOWCASE_STAR_ROUTING_POLICY_VERSION="objective-dependency-routing-v1",
            SHOWCASE_STAR_FEATURES=dict.fromkeys({"adaptive_solving", "auto_problem_spec",
                "problem_spec", "final_generation", "final_solution_review", "context_pack",
                "progress_scheduling"}, True),
            SHOWCASE_STAR_CONTEXT_CAPACITY=CAPACITY_POLICY,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=12, max_http_attempts=12))

    def submit_problem(self, problem):
        """Submit only the mathematical message and existing Job envelope."""
        response = self.client.post("/api/agent/jobs", headers=self.headers(), json={
            "message": problem, "session_id": self.session, "solver_mode": "star_limited"})
        self.assertEqual(202, response.status_code, response.get_json())
        return response.get_json()["job_id"]

    def test_intake_maps_result_dependencies_without_planning_independent_output_requirements(self):
        problem = "Evaluate 1+1, list its possible values, and explain why none are omitted."
        spec = deepcopy(SPEC)
        spec.update(original_problem=problem, root_obligations=[
            {"obligation_id": "values", "obligation_type": "enumeration",
             "statement": "List the possible values of 1+1", "prerequisite_ids": []},
            {"obligation_id": "complete", "obligation_type": "completeness",
             "statement": "Explain why no value is omitted", "prerequisite_ids": []}])
        candidate = "By standard integer addition 1+1=2. Addition has a unique value, so none is omitted."
        self.open_intake([spec, {**SOLVED, "solution_candidate": candidate}, ACCEPT])
        job_id = self.submit_problem(problem)
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final.get("error"))
        self.assertEqual(["problem_intake", "explore", "whole_solution_verifier"],
                         [r["role"] for r in self.outbound])
        self.assertEqual(problem, self.outbound[0]["original_problem"])
        instructions = "\n".join(m["content"] for m in self.outbound_messages[0]
                                 if m["role"] == "system")
        required_guidance = (
            "When a requested conclusion uses the result of another objective",
            "dependent root's prerequisite_ids",
            "dependent auxiliary goal's dependencies",
            "Use only declared objective IDs",
            "leave dependencies empty when absent",
            "Do not infer dependencies from difficulty, length",
            "the requirement to explain or list all solutions",
        )
        self.assertEqual([], [g for g in required_guidance if g not in instructions],
                         "The actual Intake HTTP system message lacks dependency field guidance")
        roots = self.outbound[1]["problem_spec"]["root_obligations"]
        self.assertEqual(["values", "complete"], [r["obligation_id"] for r in roots])
        self.assertTrue(all(not r.get("prerequisite_ids") for r in roots))
        self.assertEqual(3, final["result"]["budget"]["http_attempts"])
        self.report(job_id)
        self.client.get(f"/api/agent/jobs/{job_id}/answer")
        self.assertEqual(3, len(self.outbound))

    def test_dependency_prerequisite_objection_is_resolved_before_dependent_work(self):
        problem = "Evaluate 1+1, then use that value to justify the result."
        spec = deepcopy(SPEC)
        spec.update(original_problem=problem, root_obligations=[{
            "obligation_id": "root:conclusion", "obligation_type": "universal",
            "statement": "Justify the result using the evaluated value",
            "prerequisite_ids": ["aux:value"]}], auxiliary_goals=[{
            "goal_id": "aux:value", "description": "Evaluate the expression",
            "dependencies": []}])
        plan = {"version": 1, "steps": [
            {"step_id": "prepare", "title": "Evaluate", "objective": "Evaluate 1+1",
             "obligation_ids": [], "auxiliary_goal_ids": ["aux:value"], "method_id": "direct"},
            {"step_id": "conclude", "title": "Use the value", "objective": "Justify the result",
             "obligation_ids": ["root:conclusion"], "auxiliary_goal_ids": [],
             "depends_on": ["prepare"], "method_id": "direct"}]}
        objection = "Justify the addition before using its value."

        def reply(request):
            """Script one concrete objection at the external provider boundary."""
            role = request["role"]
            if role == "planner":
                return plan
            if role == "reasoner":
                return {"argument": "By standard integer addition 1+1=2.",
                        "claims": [{"statement": "1+1=2", "label": "hard-verify"}], "blocked": False}
            if role == "step_verifier":
                reviews = [r for r in self.outbound if r["role"] == "step_verifier"]
                if len(reviews) == 1:
                    return {"goal_gate": "PARTIAL", "logic_gate": "UNCERTAIN",
                            "verdict": "CHALLENGE", "objection": objection}
                evidence = [] if request["step"]["step_id"] == "prepare" else [{
                    "obligation_id": "root:conclusion", "evidence_category": "universal_proof",
                    "claim_indexes": [0]}]
                return {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                        "objection": "", "obligation_evidence": evidence}
            if role == "final_generator":
                return {"final_response": "By standard integer addition 1+1=2."}
            return ACCEPT

        self.open_intake([spec, *([reply] * 9)])
        job_id = self.submit_problem(problem)
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final.get("error"))
        self.assertEqual(["problem_intake", "planner", "reasoner", "step_verifier",
                          "reasoner", "step_verifier", "reasoner", "step_verifier",
                          "final_generator", "whole_solution_verifier"],
                         [r["role"] for r in self.outbound])
        reasoners = [r for r in self.outbound if r["role"] == "reasoner"]
        self.assertEqual(["prepare", "prepare", "conclude"],
                         [r["step"]["step_id"] for r in reasoners])
        self.assertEqual(objection, reasoners[1]["objection"])
        self.assertTrue(all(r["run_id"] == job_id for r in reasoners))
        self.assertTrue(all(r["problem_spec_version"] == 1 for r in self.outbound[1:]))
        planner = self.outbound[1]
        self.assertEqual([{"objective_id": "root:conclusion", "kind": "root",
                           "prerequisite_ids": ["aux:value"]},
                          {"objective_id": "aux:value", "kind": "auxiliary",
                           "prerequisite_ids": []}], planner["objective_dependencies"])
        self.assertTrue(reasoners[2]["role_context"]["state"]["accepted_results"])
        self.assertEqual(10, final["result"]["budget"]["http_attempts"])
        events = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        self.assertIn("objective_dependencies", events)
        self.assertIn("CHALLENGE", events)
        report = self.report(job_id)
        self.assertEqual("accepted", report["semantics"]["whole_review"])
        self.assertEqual("same_artifact", report["semantics"]["binding"])
        self.assertEqual(10, len(self.outbound))

