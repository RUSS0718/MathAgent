"""Controlled wire contracts, not evidence that a model obeys Intake guidance."""

import json
import unittest
from copy import deepcopy

from tests.star_product_support import StarJobFixture
from tests import test_natural_intake_job_191 as natural_tests
from tests import test_clarification_172 as clarification_tests
from tests.star_product_support import ACCEPT, SOLVED

# Independently authored synthetic deviation: workflow roots, false edges and wrong type.
# Structural acceptance is a known limitation, never a semantic oracle.
SYNTHETIC_BAD_SPEC = {
    "specification_version": 1,
    "original_problem": "Determine the rational q satisfying 8q - 5 = 19.",
    "domain": "rational numbers",
    "quantifiers": ["one unknown q"],
    "assumptions": [],
    "directions": ["isolate the unknown", "check the candidate"],
    "output_requirements": ["Report the rational solution with a justification"],
    "clarification": None,
    "applicable_condition": None,
    "formalization": {"status": "not_selected", "reason": "Synthetic intake fixture",
                      "require_formal": False, "obligation_ids": [], "target": None},
    "root_obligations": [
        {"obligation_id": "assert_witness", "obligation_type": "existence",
         "statement": "Assert a rational witness for the equation", "prerequisite_ids": []},
        {"obligation_id": "isolate_unknown", "obligation_type": "extremum_attainment",
         "statement": "Isolate q in the given equality", "prerequisite_ids": ["assert_witness"]},
        {"obligation_id": "check_candidate", "obligation_type": "filtering",
         "statement": "Check the candidate in the given equality",
         "prerequisite_ids": ["isolate_unknown"]},
    ],
    "auxiliary_goals": [],
}


class IntakeSingleGoalJobTest(StarJobFixture, unittest.TestCase):
    open_intake = natural_tests.NaturalIntakeJobTest.open_intake
    submit_problem = natural_tests.NaturalIntakeJobTest.submit_problem

    def synthetic_bad_route(self):
        self.open_intake([SYNTHETIC_BAD_SPEC, {"invalid_plan": True}, {"invalid_plan": True}])
        job_id = self.submit_problem(SYNTHETIC_BAD_SPEC["original_problem"])
        self.terminal(job_id)
        self.assertEqual(["problem_intake", "planner", "planner"],
                         [r["role"] for r in self.outbound])
        roots = self.outbound[1]["problem_spec"]["root_obligations"]
        self.assertEqual(["assert_witness", "isolate_unknown", "check_candidate"],
                         [r["obligation_id"] for r in roots])
        self.assertEqual([[], ["assert_witness"], ["isolate_unknown"]],
                         [r.get("prerequisite_ids", []) for r in roots])
        self.assertEqual([r["statement"] for r in SYNTHETIC_BAD_SPEC["root_obligations"]],
                         [r["statement"] for r in roots])
        self.assertEqual("extremum_attainment", roots[1]["obligation_type"])
        events = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        self.assertIn("objective_dependencies", events)
        return self.outbound_messages[0][0]["content"]

    def test_synthetic_bad_spec_is_still_accepted_and_routes_by_its_edges(self):
        instructions = self.synthetic_bad_route()
        self.assertIn("Record only genuine logical prerequisites", instructions)
        self.assertIn("not ordinary counting or numerical evaluation", instructions)

    def assert_single_goal_guidance(self, instructions):
        for guidance in (
            "For a request to solve one equation",
            "one user mathematical objective",
            "multiple root obligation records",
            "one scalar obligation_type per record",
            "Do not cap the number of roots",
            "Existence, algebraic manipulation and substitution checks",
            "internal work, not separate",
            "roots or auxiliary goals merely because they occur in sequence",
            "uniqueness and all-solutions completeness",
            "without inventing dependency edges",
            "separately requested conclusions",
            "ordinary equation solving is not extremum_attainment",
        ):
            self.assertIn(guidance, instructions)

    def test_all_roots_http_contract_preserves_multiple_scalar_typed_obligations(self):
        problem = "Find all real roots of t^2 + t - 12 = 0 and justify that none are missing."
        spec = deepcopy(SYNTHETIC_BAD_SPEC)
        spec.update(original_problem=problem, domain="real numbers", quantifiers=["all real t"],
                    directions=["solve the equation"], output_requirements=["List all roots and prove completeness"],
                    root_obligations=[
                        {"obligation_id": "roots", "obligation_type": "enumeration",
                         "statement": "List the real roots of the stated quadratic", "prerequisite_ids": []},
                        {"obligation_id": "exhaustive", "obligation_type": "completeness",
                         "statement": "Justify that the list omits no real root", "prerequisite_ids": []}])
        # Scripted replies test message/schema coherence and routing, not model obedience.
        self.open_intake([spec, {**SOLVED, "solution_candidate": "SYNTHETIC_ALL_ROOTS_SENTINEL"}, ACCEPT])
        final = self.terminal(self.submit_problem(problem))
        self.assertEqual("succeeded", final["status"], final.get("error"))
        self.assertEqual(["problem_intake", "explore", "whole_solution_verifier"],
                         [r["role"] for r in self.outbound])
        self.assertEqual(problem, self.outbound[0]["original_problem"])
        for request in self.outbound[1:]:
            roots = request["problem_spec"]["root_obligations"]
            self.assertEqual(["roots", "exhaustive"], [r["obligation_id"] for r in roots])
            self.assertEqual(["enumeration", "completeness"], [r["obligation_type"] for r in roots])
            self.assertEqual([r["statement"] for r in spec["root_obligations"]],
                             [r["statement"] for r in roots])
            self.assertTrue(all(not r.get("prerequisite_ids") for r in roots))
            self.assertEqual([], request["problem_spec"]["auxiliary_goals"])
        self.assertEqual(3, final["result"]["budget"]["http_attempts"])
        instructions = self.outbound_messages[0][0]["content"]
        schema, _ = json.JSONDecoder().raw_decode(instructions.split("Obey this exact response schema: ", 1)[1])
        roots_schema = schema["properties"]["root_obligations"]
        self.assertNotIn("maxItems", roots_schema)
        type_schema = roots_schema["items"]["properties"]["obligation_type"]
        self.assertIn("enumeration", type_schema["enum"])
        self.assertIn("completeness", type_schema["enum"])
        self.assertNotIn("array", type_schema.values())
        self.assertNotIn("one requested root goal", instructions)
        for guidance in ("one user mathematical objective", "multiple root obligation records",
                         "one scalar obligation_type per record", "Do not cap the number of roots",
                         "uniqueness and all-solutions completeness", "without inventing dependency edges"):
            self.assertIn(guidance, instructions)

    def test_initial_http_message_distinguishes_single_goal_from_inner_work(self):
        self.assert_single_goal_guidance(self.synthetic_bad_route())

    def test_format_repair_http_message_keeps_single_goal_contract(self):
        self.open_intake([{"invalid_spec": True}, SYNTHETIC_BAD_SPEC,
                          {"invalid_plan": True}, {"invalid_plan": True}])
        job_id = self.submit_problem(SYNTHETIC_BAD_SPEC["original_problem"])
        self.terminal(job_id)
        self.assertEqual(["problem_intake", "problem_intake", "planner", "planner"],
                         [r["role"] for r in self.outbound])
        self.assertTrue(self.outbound[1]["format_repair"])
        for messages in self.outbound_messages[:2]:
            self.assert_single_goal_guidance(messages[0]["content"])
        for messages in self.outbound_messages[2:]:
            self.assertNotIn("For a request to solve one equation", messages[0]["content"])

    def test_no_edge_goal_reaches_direct_review_without_answer_in_intake_guidance(self):
        spec = deepcopy(SYNTHETIC_BAD_SPEC)
        spec["root_obligations"] = [{"obligation_id": "solve", "obligation_type": "existence",
                                      "statement": "Find the requested real solution",
                                      "prerequisite_ids": []}]
        # A scripted answer is only a pipeline sentinel, never evidence of mathematical fidelity.
        candidate = "CONTROLLED_ANSWER_SENTINEL_206"
        self.open_intake([spec, {**SOLVED, "solution_candidate": candidate}, ACCEPT])
        final = self.terminal(self.submit_problem(SYNTHETIC_BAD_SPEC["original_problem"]))
        self.assertEqual("succeeded", final["status"], final.get("error"))
        self.assertEqual(["problem_intake", "explore", "whole_solution_verifier"],
                         [r["role"] for r in self.outbound])
        self.assertEqual(3, final["result"]["budget"]["http_attempts"])
        instructions = self.outbound_messages[0][0]["content"]
        self.assert_single_goal_guidance(instructions)
        for leak in (candidate, SYNTHETIC_BAD_SPEC["original_problem"], "8q - 5 = 19"):
            self.assertNotIn(leak, instructions)
        for messages in self.outbound_messages[1:]:
            self.assertNotIn("For a request to solve one equation", messages[0]["content"])


class IntakeSingleGoalClarificationTest(StarJobFixture, unittest.TestCase):
    open_faithful = clarification_tests.ClarificationTest.open_faithful
    waiting = clarification_tests.ClarificationTest.waiting
    answer = clarification_tests.ClarificationTest.answer
    assert_single_goal_guidance = IntakeSingleGoalJobTest.assert_single_goal_guidance

    def open_star(self, replies, **config):
        super().open_star(replies, SHOWCASE_PRESENTATION_ENABLED=True, **config)

    def test_clarification_and_its_format_repair_keep_contract_and_original_deadline(self):
        job_id, before = self.waiting(clarification_tests.SPEC, {"invalid_spec": True},
                                     clarification_tests.REASSESSED,
                                     clarification_tests.SOLVED_AREA,
                                     clarification_tests.POLISHED_AREA, ACCEPT)
        question = before["result"]["faithful"]["clarification"]
        self.assertEqual(202, self.answer(job_id, question).status_code)
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final.get("error"))
        self.assertEqual(["problem_intake"] * 3 +
                         ["explore", "explore_polish", "whole_solution_verifier"],
                         [r["role"] for r in self.outbound])
        for request, messages in zip(self.outbound[:3], self.outbound_messages[:3]):
            self.assertEqual(clarification_tests.PROBLEM, request["original_problem"])
            self.assert_single_goal_guidance(messages[0]["content"])
        self.assertEqual(clarification_tests.ANSWER,
                         self.outbound[1]["clarification_input"]["answer"])
        self.assertEqual(clarification_tests.ANSWER,
                         self.outbound[2]["clarification_input"]["answer"])
        self.assertTrue(self.outbound[2]["format_repair"])
        for messages in self.outbound_messages[3:]:
            self.assertNotIn("For a request to solve one equation", messages[0]["content"])
        self.assertEqual(before["result"]["budget"]["deadline_at"],
                         final["result"]["budget"]["deadline_at"])
        self.assertEqual(before["result"]["budget"]["limits"], final["result"]["budget"]["limits"])
        self.assertEqual(6, final["result"]["budget"]["http_attempts"])
