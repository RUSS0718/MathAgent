"""Live core producer contract used by the public formal integration tests."""

from __future__ import annotations

import unittest

from showcase.formal import normalize_formal_request, normalize_target
from showcase.solver_harness.specification import normalize_problem_spec

PROBLEM = "For every rational x, x + x = 2 * x."
RAW_SPEC = {
    "specification_version": 1,
    "original_problem": PROBLEM,
    "domain": "rationals",
    "quantifiers": ["forall x"],
    "assumptions": [],
    "directions": ["equality"],
    "output_requirements": ["state the identity"],
    "root_obligations": [{
        "obligation_id": "root:identity",
        "obligation_type": "universal",
        "statement": "x + x = 2 * x",
        "direction": "equality",
    }],
    "auxiliary_goals": [],
}
RAW_TARGET = {
    "domain": "rationals", "variables": ["x"], "lhs": "x + x", "rhs": "2 * x",
    "quantifiers": ["forall x"], "assumptions": [], "direction": "equality",
    "conclusion": "x + x = 2 * x",
}


class FormalCoreProducerContractTest(unittest.TestCase):
    def test_real_core_accepts_public_problem_spec_and_target(self):
        spec = normalize_problem_spec(RAW_SPEC)
        target = normalize_target(RAW_TARGET)
        self.assertEqual("rationals", target["domain"])
        self.assertEqual(["forall x"], target["quantifiers"])
        self.assertEqual("equality", target["direction"])
        raw = {
            "schema_version": 1, "job_id": "job", "run_id": "run",
            "attempt_id": "attempt", "parent_attempt_id": None,
            "problem": {"text": PROBLEM, "hash": ""},
            "specification": spec, "target": target,
            "policy": {
                "enabled": True, "backend": "lean_tactic_prover",
                "timeout_seconds": 30, "max_output_bytes": 16000,
                "allowed_axioms": ["propext", "Classical.choice", "Quot.sound"],
                "environment": {},
            },
            "cost": {"elapsed_seconds": 0.0, "output_bytes": 0},
            "review": None,
        }
        normalized = normalize_formal_request(raw)
        self.assertEqual("rational-polynomial-v1",
                         normalized["specifications"]["target_to_environment"]["template_version"])
        self.assertEqual(spec["root_obligations"],
                         normalized["specifications"]["original_to_spec"]["root_obligations"])
        self.assertEqual(target["hash"], normalized["target"]["hash"])


if __name__ == "__main__":
    unittest.main()
