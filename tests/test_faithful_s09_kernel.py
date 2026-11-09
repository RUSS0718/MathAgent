"""Native Lean receipt acceptance, independent of the Docker transport."""

import unittest


class NativeKernelReceiptTest(unittest.TestCase):
    def test_native_resource_usage_preserves_missing_measurements_as_unknown(self):
        from showcase.formal_kernel import resource_usage

        self.assertEqual({"memory_peak_bytes": None, "cpu_usage_usec": None}, resource_usage(""))
        self.assertEqual({"memory_peak_bytes": 4096, "cpu_usage_usec": 125}, resource_usage(
            "S09_MEMORY_PEAK_BYTES=4096\nS09_CPU_USAGE_USEC=125\n"))

    def test_independent_checker_is_required_after_kernel_receipt(self):
        from showcase.formal import LeanTacticProver, ReviewAuthority
        from showcase.formal_correspondence import CHECKER_VERSION

        problem = "For every rational x, x + x = 2 * x."
        request = {
            "schema_version": 1, "job_id": "job", "run_id": "run",
            "attempt_id": "attempt", "parent_attempt_id": None,
            "problem": {"text": problem},
            "specification": {
                "specification_version": 1, "original_problem": problem,
                "domain": "rationals", "quantifiers": ["forall x"], "assumptions": [],
                "directions": ["equality"], "output_requirements": [], "auxiliary_goals": [],
                "root_obligations": [{"obligation_id": "root:identity",
                                      "obligation_type": "universal",
                                      "statement": "x + x = 2 * x", "direction": "equality"}],
            },
            "target": {"domain": "rationals", "variables": ["x"], "lhs": "x + x",
                       "rhs": "2 * x", "quantifiers": ["forall x"],
                       "assumptions": [], "direction": "equality"},
            "policy": {"enabled": True, "backend": "lean_tactic_prover",
                       "environment": {}, "allowed_axioms": []},
        }

        class Executor:
            environment_hash = "e" * 64
            manifest = {"deployment_manifest_sha256": environment_hash,
                        "dependency_audit": {"passed": True, "packages": ["fixture-pinned"]}}

            def execute(self, source, **kwargs):
                return {"status": "success", "exit_code": 0, "cleanup_verified": True,
                        "stdout": "theorem polynomial_identity : forall x, x+x=2*x := proof\n"
                                  "'polynomial_identity' does not depend on any axioms\n",
                        "environment": self.manifest, "duration_seconds": 0.2}

        self.assertEqual("L2", LeanTacticProver(Executor()).invoke(request)["grade"])
        authority = ReviewAuthority({CHECKER_VERSION: "test-authority-secret"},
                                    {CHECKER_VERSION: "independent_service"})
        prover = LeanTacticProver(Executor(), review_authority=authority)
        reviewed = prover.invoke(request)
        self.assertEqual("L3", reviewed["grade"])
        self.assertEqual("independent_service",
                         reviewed["proof_artifact"]["independent_review"]["reviewer_type"])
        request["specification"]["root_obligations"].append({
            "obligation_id": "root:extra", "obligation_type": "universal",
            "statement": "Prove a further fact", "direction": "equality",
        })
        self.assertEqual("L2", prover.invoke(request)["grade"])

    def test_computed_zero_denominator_is_outside_the_polynomial_template(self):
        from showcase.formal_specification import normalize_target

        with self.assertRaises(ValueError):
            normalize_target({
                "domain": "rationals", "variables": ["x"],
                "lhs": "x / (1 - 1)", "rhs": "0", "quantifiers": ["forall x"],
                "assumptions": [], "direction": "equality",
            })

    def test_native_recursive_audit_requires_complete_named_output(self):
        from showcase.formal_kernel import parse_kernel_output

        native = (
            "theorem polynomial_identity : forall x, x = x := fun x => Eq.refl x\n"
            "'polynomial_identity' depends on axioms: [propext, Quot.sound]\n"
        )
        proof, audit, axioms = parse_kernel_output(native)
        self.assertIn("Eq.refl", proof)
        self.assertIn("polynomial_identity", audit)
        self.assertEqual(["propext", "Quot.sound"], axioms)
        for invalid in (
            "", native.replace("polynomial_identity", "different_goal"),
            native + "'polynomial_identity' depends on axioms: []\n",
            native.replace("Eq.refl x", "..."),
            native.replace("[propext, Quot.sound]", "[propext,"),
        ):
            with self.subTest(output=invalid), self.assertRaises(ValueError):
                parse_kernel_output(invalid)

    def test_axiom_free_native_receipt_is_distinct_from_missing_audit(self):
        from showcase.formal_kernel import parse_kernel_output

        proof, audit, axioms = parse_kernel_output(
            "theorem polynomial_identity : True := True.intro\n"
            "'polynomial_identity' does not depend on any axioms\n"
        )
        self.assertEqual([], axioms)
        self.assertTrue(proof and audit)
