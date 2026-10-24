"""Unit-level seams for the Verifier computation protocol; public entry stays authoritative."""

import unittest

from showcase.solver_harness import (
    ScriptedMetaPort,
    ScriptedModelPort,
    ScriptedToolPort,
    ScriptedVerifierPort,
    SolverHarness,
)
from showcase.solver_harness.intern_schemas import response_schema
from showcase.tool_schemas import schema_error

REQUEST = {"tool": "polynomial_check", "arguments": {"coefficients": [1]},
           "scope": "finite_computation", "expected_output": 2}
PLAN = {"version": 1, "steps": [{"step_id": "s1", "title": "t", "objective": "o"}]}
PREMATURE = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": "",
             "tool_request": REQUEST}
ACCEPT = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": ""}
CONFIG = {
    "features": {"local_code_tool": True},
    "allowed_tools": ["polynomial_check"],
    "max_model_calls": 8,
}
REPORT = {"argument": "2+2=4", "claims": [
    {"statement": "2+2=4", "label": "hard-verify"}]}


class VerifierReplySchemaTest(unittest.TestCase):
    def test_verifier_roles_may_declare_a_controlled_computation_request(self):
        for role, reply in (
            ("step_verifier", {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                               "objection": "", "tool_request": REQUEST}),
            ("whole_solution_verifier", {"verdict": "ACCEPT", "tool_request": REQUEST}),
            ("step_verifier", {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "CHALLENGE",
                               "objection": "x", "tool_request": None}),
            ("whole_solution_verifier", {"verdict": "REJECT", "reason": "x"}),
        ):
            with self.subTest(role=role, reply=reply):
                schema = response_schema({"role": role})
                self.assertIsNone(schema_error(reply, schema))

    def test_unlisted_fields_and_unknown_tools_stay_rejected(self):
        for role, reply in (
            ("step_verifier", {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                               "objection": "", "confidence": 0.95}),
            ("whole_solution_verifier", {"verdict": "ACCEPT", "tool_request": {
                "tool": "shell", "arguments": {}, "scope": "finite_computation"}}),
            ("step_verifier", {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                               "objection": "", "tool_request": {
                                   "tool": "polynomial_check", "arguments": {},
                                   "scope": "general_proof"}}),
        ):
            with self.subTest(role=role, reply=reply):
                schema = response_schema({"role": role})
                self.assertTrue(schema_error(reply, schema))


class VerifierComputeFenceTest(unittest.TestCase):
    def test_pure_reasoning_request_is_denied_and_never_executes(self):
        blocked = {"argument": "stuck", "claims": [], "blocked": True}
        guidance = {"action_type": "retry_different_method",
                    "specific_task": "Try a different route", "use_pure_reasoning": True,
                    "trace_back_to": None, "rationale": "stuck"}
        retry = {"argument": "pure", "claims": [
            {"statement": "2+2=4", "label": "hard-verify"}]}
        tool = ScriptedToolPort([])
        with SolverHarness(
            config={**CONFIG, "features": {**CONFIG["features"], "meta_guidance": True}},
            model_port=ScriptedModelPort([blocked, retry]),
            verifier_port=ScriptedVerifierPort([PREMATURE, ACCEPT]),
            meta_port=ScriptedMetaPort([guidance]),
            tool_port=tool,
        ) as harness:
            result = harness.solve("2+2", {"plan": PLAN, "run_id": "pure"})
        self.assertEqual([], tool.requests)
        self.assertEqual(0, result["state"]["counters"]["tool_calls"])
        receipt = result["state"]["tool_receipts"][-1]
        self.assertEqual("pure_reasoning_denied", receipt["reason"])
        self.assertEqual("step_verifier", receipt["source_role"])
        self.assertFalse(receipt["executed"])
        verification = result["state"]["steps"]["s1"]["verification"]
        self.assertEqual("ACCEPT", verification["verdict"])
        self.assertTrue(verification["valid"])

    def test_deadline_before_dispatch_records_denial_receipt(self):
        import time

        class SlowVerifier(ScriptedVerifierPort):
            def verify(self, request):
                time.sleep(1.01)
                return super().verify(request)

        tool = ScriptedToolPort([])
        with SolverHarness(
            config={**CONFIG, "max_total_duration_seconds": 1},
            model_port=ScriptedModelPort([REPORT]),
            verifier_port=SlowVerifier([PREMATURE, ACCEPT]),
            tool_port=tool,
        ) as harness:
            result = harness.solve("2+2", {"plan": PLAN})
        self.assertEqual([], tool.requests)
        receipt = result["state"]["tool_receipts"][-1]
        self.assertEqual("runtime_budget_exhausted", receipt["reason"])
        self.assertEqual("step_verifier", receipt["source_role"])

    def test_bound_exhaustion_leaves_pending_request_unfulfilled(self):
        other = {"goal_gate": "PARTIAL", "logic_gate": "UNCERTAIN", "verdict": "ACCEPT",
                 "objection": "", "tool_request": {
                     "tool": "polynomial_check", "arguments": {"coefficients": [2]},
                     "scope": "finite_computation", "expected_output": 2}}
        tool = ScriptedToolPort([{"status": "success", "output": 2, "exit_code": 0}])
        with SolverHarness(
            config={**CONFIG, "max_verifier_tool_requests": 1},
            model_port=ScriptedModelPort([REPORT]),
            verifier_port=ScriptedVerifierPort([PREMATURE, other, ACCEPT]),
            tool_port=tool,
        ) as harness:
            result = harness.solve("2+2", {"plan": PLAN})
        self.assertEqual(1, len(tool.requests))
        verification = result["state"]["steps"]["s1"]["verification"]
        self.assertFalse(verification["valid"])
        self.assertEqual("verifier_tool_request_unfulfilled", verification["reason"])
        self.assertNotEqual("ACCEPTED", result["state"]["steps"]["s1"]["status"])

    def test_malformed_scripted_request_is_unfulfilled_and_never_executed(self):
        malformed = {**PREMATURE, "tool_request": {
            "tool": "polynomial_check", "arguments": {}, "scope": "general_proof"}}
        tool = ScriptedToolPort([])
        with SolverHarness(
            config=CONFIG,
            model_port=ScriptedModelPort([REPORT]),
            verifier_port=ScriptedVerifierPort([malformed, ACCEPT]),
            tool_port=tool,
        ) as harness:
            result = harness.solve("2+2", {"plan": PLAN})
        self.assertEqual([], tool.requests)
        verification = result["state"]["steps"]["s1"]["verification"]
        self.assertFalse(verification["valid"])
        self.assertEqual("verifier_tool_request_unfulfilled", verification["reason"])

    def test_repeated_identical_request_reuses_committed_receipt(self):
        tool = ScriptedToolPort([{"status": "success", "output": 2, "exit_code": 0}])
        with SolverHarness(
            config=CONFIG,
            model_port=ScriptedModelPort([REPORT]),
            verifier_port=ScriptedVerifierPort([PREMATURE, PREMATURE, ACCEPT]),
            tool_port=tool,
        ) as harness:
            result = harness.solve("2+2", {"plan": PLAN, "run_id": "reuse"})
        self.assertEqual(1, len(tool.requests))
        receipts = [item for item in result["state"]["tool_receipts"]
                    if item.get("source_role") == "step_verifier"]
        self.assertEqual(1, len(receipts))
        verification = result["state"]["steps"]["s1"]["verification"]
        self.assertEqual("ACCEPT", verification["verdict"])


if __name__ == "__main__":
    unittest.main()
