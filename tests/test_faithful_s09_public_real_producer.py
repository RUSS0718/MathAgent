"""Integration contract for the public formal adapter and real core producer."""

from __future__ import annotations

import unittest

from showcase.formal import (
    LeanTacticProver,
    build_specification_records,
    normalize_formal_request,
    normalize_target,
)
from showcase.solver_harness.formal_integration import (
    FormalIntegrationState,
    run_formal_verification,
)
from showcase.solver_harness.specification import normalize_problem_spec

PROBLEM = "For every rational x, (x + 1) ^ 2 = x ^ 2 + 2 * x + 1."
RAW_SPEC = {
    "specification_version": 1, "original_problem": PROBLEM,
    "domain": "rationals", "quantifiers": ["forall x"], "assumptions": [],
    "directions": ["equality"], "output_requirements": ["state the identity"],
    "root_obligations": [{
        "obligation_id": "root:identity", "obligation_type": "universal",
        "statement": "(x + 1) ^ 2 = x ^ 2 + 2 * x + 1", "direction": "equality",
    }],
    "auxiliary_goals": [],
}
RAW_TARGET = {
    "domain": "rationals", "variables": ["x"],
    "lhs": "(x + 1) ** 2", "rhs": "x ** 2 + 2 * x + 1",
    "quantifiers": ["forall x"], "assumptions": [], "direction": "equality",
}
POLICY = {
    "enabled": True, "backend": "lean_tactic_prover", "timeout_seconds": 30,
    "max_output_bytes": 16000,
    "allowed_axioms": ["propext", "Classical.choice", "Quot.sound"],
    "environment": {},
}
class UnavailableExecutor:
    def execute(self, source, *, run_id, call_id, **kwargs):
        self.source = source
        self.run_id = run_id
        self.call_id = call_id
        return {
            "status": "unavailable", "executed": False, "cleanup_verified": True,
            "environment": {}, "duration_seconds": 0.1, "observed_output_bytes": 0,
            "stdout": "", "stderr": "lean unavailable", "reason": "lean_unavailable",
        }


class PublicFormalRealProducerTest(unittest.TestCase):
    def test_public_adapter_uses_core_schema_and_fake_transport_never_grants_l2(self):
        spec = normalize_problem_spec(RAW_SPEC)
        target = normalize_target(RAW_TARGET)
        records = build_specification_records(PROBLEM, spec, target)
        executor = UnavailableExecutor()
        backend = LeanTacticProver(executor)
        state = FormalIntegrationState(
            job_id="job-core", run_id="run-core", problem=PROBLEM,
            problem_spec={**spec, "hash": records["original_to_spec"]["problem_spec_hash"]},
            policy=POLICY, target=target,
        )
        result = run_formal_verification(state, backend=backend, target=target)
        self.assertEqual("unavailable", result["status"])
        self.assertIsNone(result["grade"])
        self.assertEqual("unavailable", result["current"]["status"])
        self.assertEqual(records, result["current"]["specifications"])
        request_value = {
            "schema_version": 1, "job_id": "job-core", "run_id": "run-core",
            "attempt_id": result["current_attempt_id"], "parent_attempt_id": None,
            "problem": {"text": PROBLEM}, "specification": spec, "target": target,
            "policy": POLICY, "cost": {"elapsed_seconds": 0, "output_bytes": 0},
            "review": None,
        }
        normalized = normalize_formal_request(request_value)
        self.assertEqual("rational-polynomial-v1",
                         normalized["specifications"]["target_to_environment"]["template_version"])
        self.assertIn("x + 1", executor.source)
        self.assertIn("^ (2)", executor.source)


if __name__ == "__main__":
    unittest.main()
