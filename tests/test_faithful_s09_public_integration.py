"""RED-to-GREEN: S09/F3 product seam independent of the Lean implementation."""

from __future__ import annotations

import copy
import unittest

from showcase.formal import normalize_target
from showcase.solver_harness.specification import normalize_problem_spec

POLICY = {
    "enabled": True,
    "requested_backend": "lean_tactic_prover",
    "allowed_backends": ["lean_tactic_prover"],
    "require_formal": False,
    "timeout_seconds": 30.0,
    "max_output_bytes": 12_000,
    "resource_limits": {"memory_mb": 512, "cpu_count": 1},
    "allowed_axioms": [],
    "environment": {
        "lean_version": "4.0.0", "mathlib_version": "test",
        "toolchain": "leanprover/lean4:v4.0.0",
        "image_digest": "sha256:" + "a" * 64,
        "manifest_digest": "b" * 64, "template_version": "poly-identity-v1",
    },
}
PROBLEM = "For every rational x, x + x = 2 * x."
SPEC = normalize_problem_spec({
    "specification_version": 1, "original_problem": PROBLEM,
    "domain": "rationals", "quantifiers": ["forall x"], "assumptions": [],
    "directions": ["equality"], "output_requirements": ["state identity"],
    "root_obligations": [{
        "obligation_id": "root:identity", "obligation_type": "universal",
        "statement": "x + x = 2 * x", "direction": "equality",
    }],
    "auxiliary_goals": [],
})
TARGET = normalize_target({
    "domain": "rationals", "variables": ["x"], "lhs": "x + x", "rhs": "2 * x",
    "quantifiers": ["forall x"], "assumptions": [], "direction": "equality",
})
SPECIFICATION = {
    "version": "1", "hash": "d" * 64,
    "original_to_spec": {"status": "reviewed", "problem_hash": "e" * 64},
    "spec_to_target": {"status": "reviewed", "target_hash": TARGET["hash"]},
    "target_to_environment": {"status": "reviewed", "environment_hash": "f" * 64},
}


class FakeFormalBackend:
    name = "lean_tactic_prover"

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def invoke(self, request):
        self.requests.append(copy.deepcopy(request))
        value = self.responses.pop(0)
        return value(request) if callable(value) else copy.deepcopy(value)


def result(request, *, status="solved", grade="L2"):
    return {
        "schema_version": 1, "status": status, "grade": grade,
        "attempt_id": request["attempt_id"],
        "parent_attempt_id": request["parent_attempt_id"],
        "proof_artifact": ({"status": status, "kernel_accepted": status == "solved",
                            "source_hash": "1" * 64, "environment_hash": "2" * 64}
                           if status == "solved" else None),
        "specifications": copy.deepcopy(SPECIFICATION),
        "cost": {"elapsed_seconds": 1.5, "output_bytes": 400},
        "lineage": {"attempts": [request["attempt_id"]]},
        "reason": None if status == "solved" else status,
    }


class FormalIntegrationProductTest(unittest.TestCase):
    def test_disabled_policy_does_not_invoke_backend_and_changes_no_answer(self):
        from showcase.solver_harness.formal_integration import (
            FormalIntegrationState,
            run_formal_verification,
        )

        backend = FakeFormalBackend([lambda request: result(request)])
        state = FormalIntegrationState(job_id="job-1", run_id="run-1", problem=PROBLEM,
                                       problem_spec=SPEC, policy={"enabled": False}, target=TARGET)
        record = run_formal_verification(state, backend=backend, target=TARGET)
        self.assertEqual("disabled", record["status"])
        self.assertIsNone(record["grade"])
        self.assertEqual([], backend.requests)
        self.assertEqual(0, record["lineage"]["total_cost"]["elapsed_seconds"])

    def test_product_requires_backend_receipt_and_never_promotes_from_request_boolean(self):
        from showcase.solver_harness.formal_integration import (
            FormalIntegrationState,
            run_formal_verification,
        )

        state = FormalIntegrationState(
            job_id="job-2", run_id="run-2", problem=PROBLEM,
            problem_spec=SPEC,
            policy=POLICY, target=TARGET,
        )
        backend = FakeFormalBackend([lambda request: result(request, grade="L2")])
        backend.verify_result = lambda request, response: response["grade"]
        record = run_formal_verification(state, backend=backend, target=TARGET,
                                         review={"reviewed": True})
        self.assertEqual("L2", record["current"]["grade"])
        self.assertEqual("L2", record["grade"])
        self.assertNotEqual("L3", record["grade"])
        self.assertIsNone(backend.requests[0]["review"])

    def test_backend_cannot_rewrite_attempt_or_parent_identity(self):
        from showcase.solver_harness.formal_integration import (
            FormalIntegrationState,
            run_formal_verification,
        )

        state = FormalIntegrationState(
            job_id="job-3", run_id="run-3", problem=PROBLEM,
            problem_spec=SPEC, policy=POLICY,
            target=TARGET,
        )

        def forged(request):
            value = result(request)
            value["attempt_id"] = "forged"
            return value

        record = run_formal_verification(state, backend=FakeFormalBackend([forged]), target=TARGET)
        self.assertEqual("unknown", record["current"]["status"])
        self.assertIsNone(record["grade"])
        self.assertEqual(record["current_attempt_id"], record["current"]["attempt_id"])

    def test_retry_creates_new_attempt_with_parent_and_accumulates_cost(self):
        from showcase.solver_harness.formal_integration import (
            FormalIntegrationState,
            retry_formal_verification,
            run_formal_verification,
        )

        backend = FakeFormalBackend([
            lambda request: {
                **result(request, status="timeout", grade=None),
                "cost": {"elapsed_seconds": 1.5, "output_bytes": 400,
                         "unknown": True, "usage": {"cpu_millis": 7}},
            },
            lambda request: {
                **result(request, status="solved", grade="L2"),
                "cost": {"elapsed_seconds": 1.5, "output_bytes": 400,
                         "usage": {"cpu_millis": 11}},
            },
        ])
        backend.verify_result = lambda request, response: response["grade"]
        state = FormalIntegrationState(
            job_id="job-4", run_id="run-4", problem=PROBLEM,
            problem_spec=SPEC, policy=POLICY,
            target=TARGET,
        )
        first = run_formal_verification(state, backend=backend, target=TARGET)
        second = retry_formal_verification(state, backend=backend, target=TARGET,
                                           expected_attempt_id=first["current_attempt_id"], existing=first, operation="retry")
        self.assertNotEqual(first["current_attempt_id"], second["current_attempt_id"])
        self.assertEqual(first["current_attempt_id"], second["current"]["parent_attempt_id"])
        self.assertEqual(2, len(backend.requests))
        self.assertEqual(3.0, second["lineage"]["total_cost"]["elapsed_seconds"])
        self.assertTrue(second["lineage"]["total_cost"]["unknown"])
        self.assertEqual(18, second["lineage"]["total_cost"]["usage"]["cpu_millis"])
        self.assertEqual("timeout", second["attempts"][0]["status"])
        self.assertEqual("solved", second["attempts"][1]["status"])

    def test_unknown_is_retained_and_not_retried_without_explicit_new_attempt(self):
        from showcase.solver_harness.formal_integration import (
            FormalIntegrationError,
            FormalIntegrationState,
            retry_formal_verification,
            run_formal_verification,
        )

        backend = FakeFormalBackend([lambda request: result(request, status="unknown", grade=None)])
        state = FormalIntegrationState(
            job_id="job-5", run_id="run-5", problem=PROBLEM,
            problem_spec=SPEC, policy=POLICY,
            target=TARGET,
        )
        record = run_formal_verification(state, backend=backend, target=TARGET)
        self.assertEqual("unknown", record["current"]["status"])
        self.assertEqual(1, len(backend.requests))
        auto = run_formal_verification(state, backend=backend, target=TARGET, existing=record)
        self.assertEqual(record["current_attempt_id"], auto["current_attempt_id"])
        self.assertEqual(1, len(backend.requests))
        with self.assertRaisesRegex(FormalIntegrationError, "explicit"):
            retry_formal_verification(state, backend=backend, target=TARGET,
                                       expected_attempt_id="not-current", existing=record,
                                       operation="retry")

    def test_backend_exception_and_unverified_grade_fail_closed_with_attempt_identity(self):
        from showcase.solver_harness.formal_integration import (
            FormalIntegrationState,
            run_formal_verification,
        )

        class RaisingBackend(FakeFormalBackend):
            def invoke(self, request):
                self.requests.append(copy.deepcopy(request))
                raise TimeoutError("backend timeout")

        timeout_record = run_formal_verification(
            FormalIntegrationState("job-timeout", "run-timeout", PROBLEM, SPEC, POLICY, TARGET),
            backend=RaisingBackend([]), target=TARGET,
        )
        self.assertEqual("timeout", timeout_record["status"])
        self.assertIsNone(timeout_record["grade"])
        self.assertEqual(timeout_record["current_attempt_id"], timeout_record["current"]["attempt_id"])
        self.assertTrue(timeout_record["current"]["cost"]["unknown"])

        backend = FakeFormalBackend([lambda request: result(request, status="solved", grade="L2")])
        backend.verify_result = lambda request, response: None
        failed = run_formal_verification(
            FormalIntegrationState("job-invalid", "run-invalid", PROBLEM, SPEC, POLICY, TARGET),
            backend=backend, target=TARGET,
        )
        self.assertEqual("failed", failed["status"])
        self.assertIsNone(failed["grade"])
        self.assertEqual("formal_receipt_unverified", failed["current"]["reason"])

        timeout_backend = FakeFormalBackend([
            lambda request: result(request, status="timeout", grade="L2"),
        ])
        timeout_backend.verify_result = lambda request, response: response["grade"]
        timeout = run_formal_verification(
            FormalIntegrationState("job-timeout-grade", "run-timeout-grade",
                                   PROBLEM, SPEC, POLICY, TARGET),
            backend=timeout_backend, target=TARGET,
        )
        self.assertEqual("timeout", timeout["status"])
        self.assertIsNone(timeout["grade"])

        no_grade_backend = FakeFormalBackend([
            lambda request: result(request, status="solved", grade=None),
        ])
        no_grade_backend.verify_result = lambda request, response: None
        no_grade = run_formal_verification(
            FormalIntegrationState("job-no-grade", "run-no-grade", PROBLEM, SPEC, POLICY, TARGET),
            backend=no_grade_backend, target=TARGET,
        )
        self.assertEqual("failed", no_grade["status"])
        self.assertIsNone(no_grade["grade"])


if __name__ == "__main__":
    unittest.main()
