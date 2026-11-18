"""Dispatch reservation and recovery contracts for the product formal adapter."""

from __future__ import annotations

import tempfile
import unittest
from contextlib import closing

from showcase.formal import normalize_target
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits
from showcase.solver_harness.formal_integration import (
    FormalIntegrationState,
    mark_inflight_unknown,
    reserve_formal_attempt,
)
from showcase.solver_harness.specification import normalize_problem_spec

PROBLEM = "For every rational x, x + x = 2 * x."
SPEC = normalize_problem_spec({
    "specification_version": 1, "original_problem": PROBLEM,
    "domain": "rationals", "quantifiers": ["forall x"], "assumptions": [],
    "directions": ["equality"], "output_requirements": ["state identity"],
    "root_obligations": [{"obligation_id": "root:identity",
                          "obligation_type": "universal",
                          "statement": "x + x = 2 * x", "direction": "equality"}],
    "auxiliary_goals": [],
})
TARGET = normalize_target({"domain":"rationals", "variables":["x"],
                           "lhs":"x + x", "rhs":"2 * x",
                           "quantifiers":["forall x"], "assumptions":[],
                           "direction":"equality"})
POLICY = {"enabled": True, "backend": "lean_tactic_prover", "timeout_seconds": 30,
          "max_output_bytes": 12000, "allowed_axioms": [],
          "environment": {}, "target": TARGET}


class FormalDispatchRecoveryTest(unittest.TestCase):
    def test_reservation_is_persisted_before_dispatch_and_unknown_has_no_auto_retry(self):
        state = FormalIntegrationState("job","run",PROBLEM,SPEC,POLICY,TARGET)
        record = reserve_formal_attempt(state, existing=None)
        self.assertEqual("dispatched", record["current"]["status"])
        self.assertEqual(1, len(record["attempts"]))
        attempt_id = record["current_attempt_id"]
        unknown = mark_inflight_unknown(record)
        self.assertEqual("unknown", unknown["current"]["status"])
        self.assertIsNone(unknown["grade"])
        self.assertTrue(unknown["current"]["cost"]["unknown"])
        again = reserve_formal_attempt(state, existing=unknown)
        self.assertEqual(attempt_id, again["current_attempt_id"])
        self.assertEqual(1, len(again["attempts"]))

    def test_public_formal_execution_enters_registered_tool_registry_once(self):
        from showcase.formal import register_formal
        from showcase.run_budget import bind_budget
        from showcase.solver_harness.formal_integration import (
            execute_reserved_attempt,
            reserve_formal_attempt,
        )
        from showcase.tools import ToolRegistry

        class Backend:
            name = "lean_tactic_prover"
            timeout_seconds = 10
            calls = 0

            def invoke(self, request):
                self.calls += 1
                return {
                    "status": "unknown", "grade": None,
                    "attempt_id": request["attempt_id"],
                    "parent_attempt_id": request["parent_attempt_id"],
                    "proof_artifact": None, "specifications": request["specifications"],
                    "cost": {"elapsed_seconds": 0.2, "output_bytes": 3},
                    "lineage": {}, "reason": "transport_unknown",
                }

        backend = Backend()
        registry = ToolRegistry()
        spec = register_formal(registry, backend)
        self.assertIn("formal_verification", spec.capabilities)
        state = FormalIntegrationState("job", "run", PROBLEM, SPEC, POLICY, TARGET)
        reserved = reserve_formal_attempt(state)
        with tempfile.TemporaryDirectory() as folder, closing(
                RunBudgetLedger(database_path=folder + "/budget.sqlite")) as ledger:
            ledger.ensure("run", RunBudgetLimits(
                max_model_calls=0, max_http_attempts=0, max_tool_calls=1,
                max_tokens=100, max_runtime_seconds=30,
            ))
            with bind_budget(ledger.ensure("run", RunBudgetLimits(
                    max_model_calls=0, max_http_attempts=0, max_tool_calls=1,
                    max_tokens=100, max_runtime_seconds=30))):
                result = execute_reserved_attempt(
                    state, backend=backend, record=reserved, registry=registry,
                )
            budget = ledger.snapshot("run")
        self.assertEqual("unknown", result["status"])
        self.assertIsNone(result["grade"])
        self.assertEqual(1, backend.calls)
        self.assertEqual(1, budget["tool_calls"])
        self.assertEqual(1, budget["unknown_tool_calls"])

    def test_fake_transport_paid_once_through_run_tool_budget(self):
        with tempfile.TemporaryDirectory() as folder, closing(RunBudgetLedger(database_path=folder + "/budget.sqlite")) as ledger:
            ledger.ensure("run-tool", RunBudgetLimits(
                max_model_calls=0, max_http_attempts=0, max_tool_calls=1,
                max_tokens=100, max_runtime_seconds=30,
            ))
            action_id, _ = ledger.reserve("run-tool", "tool", role="formal_verification")
            ledger.settle("run-tool", action_id, {
                "status": "unknown", "duration_seconds": 0.2,
                "execution_evidence": {"unknown_outcome": True, "cleanup_verified": True},
            })
            budget = ledger.snapshot("run-tool")
            self.assertEqual(1, budget["tool_calls"])
            self.assertEqual(1, budget["unknown_tool_calls"])


if __name__ == "__main__":
    unittest.main()
