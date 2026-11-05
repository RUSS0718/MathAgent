"""A non-accepting review may retain an already completed computation without replay."""

import unittest
from unittest.mock import Mock

from showcase.solver_harness import (
    ScriptedModelPort,
    ScriptedToolPort,
    ScriptedVerifierPort,
    SolverHarness,
)
from showcase.solver_harness.verifier_compute import continue_review, request_digest
from tests.test_solver_harness_verifier_compute import ACCEPT, CONFIG, PLAN, REPORT


class RepeatedReceiptChallengeTest(unittest.TestCase):
    def test_real_challenge_path_continues_with_one_tool_execution(self):
        request = {"tool": "python_math", "arguments": {"code": "print(1)"}, "scope": "finite_computation"}
        challenge = {"verdict": "CHALLENGE", "goal_gate": "PARTIAL", "logic_gate": "FAIL",
                     "objection": "Provide the missing derivation", "tool_request": request}
        tool = ScriptedToolPort([{"status": "success", "output": "1", "exit_code": 0}], tools=("python_math",))
        with SolverHarness(config={**CONFIG, "allowed_tools": ["python_math"]},
                           model_port=ScriptedModelPort([REPORT, REPORT]),
                           verifier_port=ScriptedVerifierPort([challenge, challenge, ACCEPT]),
                           tool_port=tool) as harness:
            result = harness.solve("Compute", {"run_id": "repeat-challenge", "plan": PLAN})
        self.assertEqual(1, len(tool.requests))
        self.assertEqual("ACCEPTED", result["state"]["steps"]["s1"]["status"])
        self.assertEqual(1, result["state"]["counters"]["tool_calls"])

    def check_reply(self, verdict, status="success"):
        request = {"tool": "python_math", "arguments": {"code": "print(1)"}, "scope": "finite_computation"}
        receipt = {"source_role": "step_verifier", "step_id": "s1", "review_round": 1,
                   "attempt_index": 0, "request_digest": request_digest(request),
                   "request_index": 0, "status": status, "executed": True,
                   "output_available": status == "success", "exit_code": 0 if status == "success" else None}
        run = {"state": {"tool_receipts": [receipt]}}
        reply = {"verdict": verdict, "goal_gate": "PARTIAL", "logic_gate": "FAIL",
                 "objection": "The proof still lacks a step", "tool_request": request}
        dispatch = Mock(side_effect=AssertionError("must not redispatch"))
        _, result, unfulfilled = continue_review(
            Mock(), run, role="step_verifier", step_id="s1", round_number=1,
            attempt_index=0, base_call_id="review", base_request={}, reply=reply,
            reserve_and_dispatch=dispatch, reply_from="review:tool-1",
        )
        dispatch.assert_not_called()
        self.assertIn("tool_request", reply)
        return result, unfulfilled

    def test_successful_receipt_allows_explicit_challenge_without_reexecution(self):
        result, unfulfilled = self.check_reply("CHALLENGE")
        self.assertFalse(unfulfilled)
        self.assertNotIn("tool_request", result)
        self.assertEqual("CHALLENGE", result["verdict"])

    def test_repeated_accept_or_failed_receipt_still_stops(self):
        for verdict, status in (("ACCEPT", "success"), ("CHALLENGE", "tool_error"),
                                ("CHALLENGE", "unknown_outcome")):
            with self.subTest(verdict=verdict, status=status):
                _, unfulfilled = self.check_reply(verdict, status)
                self.assertTrue(unfulfilled)
