"""A local formal success must not satisfy an unproved whole problem."""

import unittest

from showcase.formal_requirements import assess_formal_requirement
from showcase.formal_specification import canonical_identity, normalize_target, public_target
from showcase.solver_harness.formal_integration import FormalIntegrationState, reserve_formal_retry
from showcase.star_result_semantics import result_semantics
from showcase.workspace import _apply_formal_requirement


class FormalRequirementTest(unittest.TestCase):
    def test_retry_reservation_invalidates_previous_requirement_assessment(self):
        policy = {"enabled": True, "backend": "lean_tactic_prover", "require_formal": True}
        state = FormalIntegrationState("j", "r", "p", {}, policy, {})
        backend = type("Backend", (), {"name": "lean_tactic_prover"})()
        old = {"current_attempt_id": "f1", "status": "solved", "grade": "L3",
               "current": {"attempt_id": "f1", "status": "solved", "grade": "L3"},
               "attempts": [], "assessment": {"status": "met"}}
        retry = reserve_formal_retry(state, existing=old, expected_attempt_id="f1",
                                     operation="retry", backend=backend)
        self.assertNotEqual("met", retry.get("assessment", {}).get("status"))

    def test_local_success_does_not_satisfy_whole_machine_requirement(self):
        for grade in ("L2", "L3"):
            with self.subTest(grade=grade):
                policy = {"require_formal": True}
                formal = {"status": "solved", "grade": grade}
                run = {"state": {"status": "completed_llm_reviewed", "phase": "TERMINAL",
                                 "calls": {}, "formal_policy": policy,
                                 "formal_verification": formal}}
                self.assertEqual("unmet", result_semantics(run, "")["formal_requirement"])
                result = {"formal_policy": policy, "formal_verification": formal,
                          "solver": {"semantics": {}}}
                _apply_formal_requirement(result)
                self.assertEqual("unmet", result["solver"]["semantics"]["formal_requirement"])

        target = public_target(normalize_target({
            "domain": "rationals", "variables": ["x"], "lhs": "x+x", "rhs": "2*x",
            "quantifiers": ["forall x"], "assumptions": [], "direction": "equality"}))
        spec = {"root_obligations": [{"obligation_id": "a"}, {"obligation_id": "b"}]}
        policy = {"require_formal": True, "target": target}
        current = {"attempt_id": "f1", "status": "solved", "grade": "L3",
                   "proof_artifact": {"accepted": True, "kernel_exit": 0,
                                      "cleanup_verified": True, "target_hash": target["hash"],
                                      "environment_hash": "e" * 64},
                   "specifications": {
                       "original_to_spec": {"review_status": "reviewed",
                           "problem_spec_hash": canonical_identity(spec),
                           "root_obligations": spec["root_obligations"][:1]},
                       "spec_to_target": {"review_status": "reviewed", "target_hash": target["hash"]},
                       "target_to_environment": {"review_status": "reviewed",
                           "target_hash": target["hash"], "environment_hash": "e" * 64}}}
        formal = {"current": current, "current_attempt_id": "f1", "status": "solved", "grade": "L3"}
        self.assertEqual("formal_coverage_incomplete", assess_formal_requirement(policy, formal, spec)["reason"])
        current["specifications"]["original_to_spec"]["root_obligations"] = spec["root_obligations"]
        self.assertEqual("met", assess_formal_requirement(policy, formal, spec)["status"])
        policy["requirement"] = {"scope": "formal_target", "minimum_grade": "L2", "target_hash": "wrong"}
        self.assertEqual("unmet", assess_formal_requirement(policy, formal, spec)["status"])
