"""Unit seams for the Explore computation protocol; public entry stays authoritative."""

import unittest

from showcase.solver_harness import (
    ScriptedModelPort,
    ScriptedToolPort,
    SolverHarness,
)
from showcase.solver_harness.intern_schemas import response_schema
from showcase.solver_harness.tool_precheck import allowed_tool_ids
from showcase.tool_schemas import schema_error

REQUEST = {"tool": "polynomial_check", "arguments": {"coefficients": [1]},
           "scope": "finite_computation", "expected_output": 2}
PROBE = {"assessment": "SOLVED", "worked": [], "failed": [], "candidates": [],
         "solution_candidate": "2", "tool_request": REQUEST}
NEED_PLAN = {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []}
CONFIG = {
    "features": {"local_code_tool": True},
    "allowed_tools": ["polynomial_check"],
    "max_model_calls": 8,
}


class ExploreReplySchemaTest(unittest.TestCase):
    def test_explore_may_declare_a_controlled_computation_request(self):
        for reply in (
            PROBE,
            {**NEED_PLAN, "tool_request": None},
            {**NEED_PLAN, "tool_request": {
                "tool": "python_math", "arguments": {"code": "print(1)"},
                "scope": "finite_computation"}},
        ):
            with self.subTest(reply=reply):
                schema = response_schema({"role": "explore"})
                self.assertIsNone(schema_error(reply, schema))

    def test_unlisted_fields_unknown_tools_and_scopes_stay_rejected(self):
        for reply in (
            {**NEED_PLAN, "confidence": 0.95},
            {**NEED_PLAN, "tool_request": {
                "tool": "shell", "arguments": {}, "scope": "finite_computation"}},
            {**NEED_PLAN, "tool_request": {
                "tool": "polynomial_check", "arguments": {}, "scope": "general_proof"}},
        ):
            with self.subTest(reply=reply):
                schema = response_schema({"role": "explore"})
                self.assertTrue(schema_error(reply, schema))


class ExploreToolPermissionTest(unittest.TestCase):
    def test_explore_advertises_the_same_local_tools_as_the_compute_roles(self):
        run = {"run_id": "r", "state": {"reasoning_mode": "reasoner"}}
        config = {"features": {"local_code_tool": True}, "allowed_tools": ["polynomial_check"]}
        port = ScriptedToolPort([])
        self.assertEqual(["polynomial_check"], allowed_tool_ids(run, "explore", config, port))
        for role in ("meta", "meta_strategist", "researcher", "explore_polish"):
            self.assertEqual([], allowed_tool_ids(run, role, config, port), role)


class ExploreComputeFenceTest(unittest.TestCase):
    def test_unpermitted_tool_config_denies_execution_and_continues(self):
        tool = ScriptedToolPort([])
        with SolverHarness(
            config={"features": {}, "allowed_tools": ["polynomial_check"],
                    "max_model_calls": 8},
            model_port=ScriptedModelPort([PROBE, NEED_PLAN]),
            tool_port=tool,
        ) as harness:
            result = harness.solve("2+2", {"run_id": "denied"})
        self.assertEqual([], tool.requests)
        self.assertEqual(0, result["state"]["counters"]["tool_calls"])
        receipt = result["state"]["tool_receipts"][-1]
        self.assertEqual("tool_not_allowed", receipt["reason"])
        self.assertEqual("explore", receipt["source_role"])
        self.assertFalse(receipt["executed"])
        finding = result["state"]["exploration_findings"][0]
        self.assertEqual("unverified_exploration", finding["provenance"])
        self.assertFalse(finding["computation"]["receipts"][0]["executed"])
        self.assertEqual("PLAN", result["state"]["phase"])

    def test_bound_exhaustion_leaves_the_second_request_unfulfilled(self):
        other = {**PROBE, "tool_request": {
            "tool": "polynomial_check", "arguments": {"coefficients": [2]},
            "scope": "finite_computation", "expected_output": 2}}
        tool = ScriptedToolPort([
            {"status": "success", "output": 2, "exit_code": 0},
            {"status": "success", "output": 2, "exit_code": 0},
        ])
        with SolverHarness(
            config={**CONFIG, "max_verifier_tool_requests": 1},
            model_port=ScriptedModelPort([PROBE, other, NEED_PLAN]),
            tool_port=tool,
        ) as harness:
            result = harness.solve("2+2", {"run_id": "bounded"})
        self.assertEqual(1, len(tool.requests))
        self.assertEqual(1, result["state"]["counters"]["tool_calls"])
        finding = result["state"]["exploration_findings"][0]
        self.assertEqual("UNKNOWN", finding["assessment"])
        self.assertEqual(
            "explore_tool_request_unfulfilled", finding["computation"]["unfulfilled"])
        self.assertEqual("PLAN", result["state"]["phase"])

    def test_repeated_identical_request_reuses_committed_receipt(self):
        tool = ScriptedToolPort([{"status": "success", "output": 2, "exit_code": 0}])
        with SolverHarness(
            config=CONFIG,
            model_port=ScriptedModelPort([PROBE, PROBE, NEED_PLAN]),
            tool_port=tool,
        ) as harness:
            result = harness.solve("2+2", {"run_id": "reuse"})
        self.assertEqual(1, len(tool.requests))
        receipts = [item for item in result["state"]["tool_receipts"]
                    if item.get("source_role") == "explore"]
        self.assertEqual(1, len(receipts))
        self.assertTrue(receipts[0]["receipt_id"].startswith("explore-tool:"))
        self.assertEqual("UNKNOWN", result["state"]["exploration_findings"][0]["assessment"])

    def test_tool_failure_is_recorded_and_exploration_continues(self):
        tool = ScriptedToolPort([{"status": "tool_error", "output": None, "exit_code": None}])
        with SolverHarness(
            config=CONFIG,
            model_port=ScriptedModelPort([PROBE, NEED_PLAN]),
            tool_port=tool,
        ) as harness:
            result = harness.solve("2+2", {"run_id": "tool-error"})
        self.assertEqual(1, len(tool.requests))
        finding = result["state"]["exploration_findings"][0]
        computed = finding["computation"]["receipts"][0]
        self.assertEqual("tool_error", computed["status"])
        self.assertTrue(computed["unknown_outcome"] is False)
        self.assertIsNone(computed["output"])


if __name__ == "__main__":
    unittest.main()
