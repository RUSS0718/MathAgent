"""A rejected computation carries actionable, safe feedback to its reviewer."""

import json
import unittest
from copy import deepcopy

from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort, SolverHarness
from showcase.solver_harness.intern_port import InternModelPort
from showcase.solver_harness.intern_schemas import response_schema
from showcase.solver_harness.tool_ports import RegistryToolPort
from showcase.tool_schemas import POLYNOMIAL_CHECK_SCHEMA
from showcase.tools import ToolRegistry
from tests.test_solver_harness_verifier_compute import ACCEPT, CONFIG, PLAN, REPORT


class VerifierToolFailureFeedbackTest(unittest.TestCase):
    def test_actual_provider_messages_retain_error_and_argument_schema(self):
        request = {"role": "step_verifier", "problem": "Compute", "allowed_tools": ["polynomial_check"],
                   "report": {"tool_receipts": [{"status": "tool_error", "error_category": "tool_schema_invalid"}]}}
        messages = InternModelPort()._messages(request, response_schema(request))
        context = json.loads(messages[-1]["content"])
        self.assertEqual("tool_schema_invalid", context["report"]["tool_receipts"][0]["error_category"])
        self.assertEqual(POLYNOMIAL_CHECK_SCHEMA, context["tool_argument_schemas"]["polynomial_check"])
        self.assertIn("Never repeat an identical failed request", messages[0]["content"])

    def test_schema_rejection_can_be_corrected_within_existing_scope_bound(self):
        registry = ToolRegistry()
        registry.register_polynomial_check()
        valid = {"schema_version": 1, "variable": "x", "coefficients": ["1", "-1"],
                 "domain": {"kind": "real"}, "candidates": ["1"]}
        invalid = {**valid, "coefficients": ["a", "-1"], "candidates": ["a"]}
        replies = [{**ACCEPT, "tool_request": {"tool": "polynomial_check", "arguments": args,
                    "scope": "finite_computation"}} for args in (invalid, valid)] + [ACCEPT]
        verifier = ScriptedVerifierPort(replies)
        with SolverHarness(config=CONFIG, model_port=ScriptedModelPort([REPORT]),
                           verifier_port=verifier, tool_port=RegistryToolPort(registry)) as harness:
            run = harness.solve("Compute", {"run_id": "feedback", "plan": PLAN})
        receipts = run["state"]["tool_receipts"]
        self.assertEqual("tool_schema_invalid", receipts[0].get("error_category"))
        self.assertEqual("success", receipts[1]["status"])
        self.assertEqual(2, run["state"]["counters"]["tool_calls"])
        self.assertEqual("ACCEPTED", run["state"]["steps"]["s1"]["status"])

    def test_arbitrary_tool_error_text_is_not_saved_as_a_category(self):
        class Port:
            source = "scripted"
            registered_tools = {"polynomial_check"}

            def execute(self, request):
                return {"status": "tool_error", "error": "private prompt and credential", "output": None}

        from showcase.solver_harness.tool_precheck import _execute

        with SolverHarness(config=CONFIG) as harness:
            run = harness.solve("Compute", {"run_id": "safe-feedback"})
            run, receipt = _execute(harness, run, {
                "tool": "polynomial_check", "arguments": {}, "scope": "finite_computation",
            }, deepcopy(CONFIG), Port(), "s1", 0)
        self.assertNotIn("private", str(receipt))
        self.assertIsNone(receipt.get("error_category"))
