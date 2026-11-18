"""Controlled wire contracts, not evidence that a model obeys Intake guidance."""

import unittest
from copy import deepcopy

from tests.star_product_support import StarJobFixture
from tests import test_natural_intake_job_191 as natural_tests
from tests import test_clarification_172 as clarification_tests
from tests.star_product_support import ACCEPT, SOLVED

# Exact captured response from #206 A-simple terminal-diagnostic.json (2026-11-18).
# Excludes only ledger-added usage, which is not a provider response field.
# Deliberately retains the known semantic/type deviation; never a valid oracle.
CAPTURED = {
    "applicable_condition": None,
    "assumptions": [
        "3x + 2 = 11 是关于实数 x 的线性方程"
    ],
    "auxiliary_goals": [],
    "clarification": None,
    "directions": [
        "求解 x",
        "验证解满足原方程"
    ],
    "domain": "实数",
    "formalization": {
        "obligation_ids": [],
        "reason": "原问题为单变量一次方程求解，不是无条件的有理多项式恒等式，因此不适合表示为 universal 目标。",
        "require_formal": False,
        "status": "unsupported",
        "target": None
    },
    "original_problem": "求实数 x，使 3x + 2 = 11。",
    "output_requirements": [
        "给出 x 的具体数值",
        "确认该数值代入原方程成立"
    ],
    "quantifiers": [
        "存在唯一的 x"
    ],
    "root_obligations": [
        {
            "direction": None,
            "obligation_id": "existence_solution",
            "obligation_type": "existence",
            "prerequisite_ids": [],
            "statement": "存在实数 x 满足 3x + 2 = 11"
        },
        {
            "direction": None,
            "obligation_id": "find_x",
            "obligation_type": "extremum_attainment",
            "prerequisite_ids": [
                "existence_solution"
            ],
            "statement": "求出满足 3x + 2 = 11 的唯一实数 x 的值"
        },
        {
            "direction": None,
            "obligation_id": "verify_solution",
            "obligation_type": "filtering",
            "prerequisite_ids": [
                "find_x"
            ],
            "statement": "验证所求 x 代入 3x + 2 = 11 后等式成立"
        }
    ],
    "specification_version": 1
}


class IntakeSingleGoalJobTest(StarJobFixture, unittest.TestCase):
    open_intake = natural_tests.NaturalIntakeJobTest.open_intake
    submit_problem = natural_tests.NaturalIntakeJobTest.submit_problem

    def captured_route(self):
        self.open_intake([CAPTURED, {"invalid_plan": True}, {"invalid_plan": True}])
        job_id = self.submit_problem(CAPTURED["original_problem"])
        self.terminal(job_id)
        self.assertEqual(["problem_intake", "planner", "planner"],
                         [r["role"] for r in self.outbound])
        roots = self.outbound[1]["problem_spec"]["root_obligations"]
        self.assertEqual(["existence_solution", "find_x", "verify_solution"],
                         [r["obligation_id"] for r in roots])
        self.assertEqual([[], ["existence_solution"], ["find_x"]],
                         [r.get("prerequisite_ids", []) for r in roots])
        self.assertEqual([r["statement"] for r in CAPTURED["root_obligations"]],
                         [r["statement"] for r in roots])
        self.assertEqual("extremum_attainment", roots[1]["obligation_type"])
        events = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        self.assertIn("objective_dependencies", events)
        return self.outbound_messages[0][0]["content"]

    def test_captured_bad_spec_is_still_accepted_and_routes_by_its_edges(self):
        instructions = self.captured_route()
        self.assertIn("Record only genuine logical prerequisites", instructions)
        self.assertIn("not ordinary counting or numerical evaluation", instructions)

    def assert_single_goal_guidance(self, instructions):
        for guidance in (
            "For a request to solve one equation",
            "one requested root goal",
            "existence, algebraic manipulation and substitution checks",
            "internal work, not separate roots or auxiliary goals",
            "uniqueness or all-solutions completeness",
            "proof requirements of that same goal",
            "separately requested conclusions",
            "ordinary equation solving is not extremum_attainment",
        ):
            self.assertIn(guidance, instructions)

    def test_initial_http_message_distinguishes_single_goal_from_inner_work(self):
        self.assert_single_goal_guidance(self.captured_route())

    def test_format_repair_http_message_keeps_single_goal_contract(self):
        self.open_intake([{"invalid_spec": True}, CAPTURED,
                          {"invalid_plan": True}, {"invalid_plan": True}])
        job_id = self.submit_problem(CAPTURED["original_problem"])
        self.terminal(job_id)
        self.assertEqual(["problem_intake", "problem_intake", "planner", "planner"],
                         [r["role"] for r in self.outbound])
        self.assertTrue(self.outbound[1]["format_repair"])
        for messages in self.outbound_messages[:2]:
            self.assert_single_goal_guidance(messages[0]["content"])
        for messages in self.outbound_messages[2:]:
            self.assertNotIn("For a request to solve one equation", messages[0]["content"])

    def test_no_edge_goal_reaches_direct_review_without_answer_in_intake_guidance(self):
        spec = deepcopy(CAPTURED)
        spec["root_obligations"] = [{"obligation_id": "solve", "obligation_type": "existence",
                                      "statement": "Find the requested real solution",
                                      "prerequisite_ids": []}]
        # A scripted answer is only a pipeline sentinel, never evidence of mathematical fidelity.
        candidate = "CONTROLLED_ANSWER_SENTINEL_206"
        self.open_intake([spec, {**SOLVED, "solution_candidate": candidate}, ACCEPT])
        final = self.terminal(self.submit_problem(CAPTURED["original_problem"]))
        self.assertEqual("succeeded", final["status"], final.get("error"))
        self.assertEqual(["problem_intake", "explore", "whole_solution_verifier"],
                         [r["role"] for r in self.outbound])
        self.assertEqual(3, final["result"]["budget"]["http_attempts"])
        instructions = self.outbound_messages[0][0]["content"]
        self.assert_single_goal_guidance(instructions)
        for leak in (candidate, CAPTURED["original_problem"], "3x + 2 = 11", "x = 3"):
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
