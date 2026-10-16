import unittest

from showcase.polynomial import PolynomialChecker
from showcase.tools import ToolRegistry

VALID = {
    "schema_version": 1,
    "variable": "x",
    "coefficients": ["1", "0", "-1"],
    "domain": {"kind": "real"},
    "candidates": ["1", "-1"],
}


class PolynomialCheckerTest(unittest.TestCase):
    def test_exact_pass_keeps_coverage_unknown(self):
        result = PolynomialChecker().check(VALID)
        self.assertEqual("pass", result["candidate_status"])
        self.assertEqual("unknown", result["coverage_status"])
        self.assertEqual(["0", "0"], [item["residual"] for item in result["candidates"]])
        self.assertTrue(result["evidence_id"])
        self.assertIn("完整解集", " ".join(result["limitations"]))

    def test_conflict_and_duplicate_are_reported(self):
        payload = {**VALID, "candidates": ["1", "1", "2"]}
        result = PolynomialChecker().check(payload)
        self.assertEqual("conflict", result["candidate_status"])
        self.assertEqual("conflict", result["coverage_status"])
        self.assertEqual(["1"], result["duplicates"])
        self.assertEqual("conflict", result["candidates"][2]["status"])

    def test_invalid_schema_is_unknown_without_evaluation(self):
        payload = {**VALID, "coefficients": ["01", "1"], "candidates": ["x"]}
        result = PolynomialChecker().check(payload)
        self.assertEqual("unknown", result["candidate_status"])
        self.assertEqual("unknown", result["coverage_status"])
        self.assertTrue(result["limitations"])
        self.assertEqual([], result["candidates"])

    def test_interval_boundary_is_checked_exactly(self):
        payload = {**VALID, "domain": {"kind": "interval", "left": "-1", "right": "1", "left_closed": True, "right_closed": False}}
        result = PolynomialChecker().check(payload)
        self.assertEqual("unknown", result["candidate_status"])
        self.assertEqual([False, True], [item["in_domain"] for item in result["candidates"]])

    def test_registry_exposes_polynomial_checker(self):
        registry = ToolRegistry()
        registry.register_polynomial_check()
        result = registry.invoke("polynomial_check", VALID)
        self.assertEqual("success", result.status)
        self.assertEqual("pass", result.value["candidate_status"])

    def test_external_case_matrix_covers_pass_conflict_and_unknown(self):
        cases = [
            ({**VALID, "coefficients": ["1", "0", "-1"], "candidates": ["1"]}, "pass"),
            ({**VALID, "coefficients": ["1", "1", "0"], "candidates": ["0", "-1"]}, "pass"),
            ({**VALID, "coefficients": ["1", "0", "0", "0"], "candidates": ["0"]}, "pass"),
            ({**VALID, "coefficients": ["1", "-2", "1"], "candidates": ["1"]}, "pass"),
            ({**VALID, "coefficients": ["1", "0", "-4"], "candidates": ["2", "-2"]}, "pass"),
            ({**VALID, "coefficients": ["1", "0", "0", "-1"], "candidates": ["1"]}, "pass"),
            ({**VALID, "candidates": ["0"]}, "conflict"),
            ({**VALID, "candidates": ["2"]}, "conflict"),
            ({**VALID, "candidates": ["1", "1"]}, "conflict"),
            ({**VALID, "candidates": ["1", "-1", "0"]}, "conflict"),
            ({**VALID, "domain": {"kind": "interval", "left": "0", "right": "1"}, "candidates": ["-1"]}, "unknown"),
            ({**VALID, "coefficients": ["1", "0", "0", "0", "0", "0"], "candidates": ["0"]}, "unknown"),
            ({**VALID, "coefficients": ["01", "1"], "candidates": ["1"]}, "unknown"),
            ({**VALID, "coefficients": ["1", "0"], "candidates": ["x"]}, "unknown"),
            ({**VALID, "domain": {"kind": "complex"}, "candidates": ["1"]}, "unknown"),
            ({**VALID, "domain": {"kind": "interval", "left": "2", "right": "1"}, "candidates": ["1"]}, "unknown"),
            ({**VALID, "variable": "x,y", "candidates": ["1"]}, "unknown"),
            ({**VALID, "schema_version": 2, "candidates": ["1"]}, "unknown"),
        ]
        for payload, expected in cases:
            with self.subTest(payload=payload):
                self.assertEqual(expected, PolynomialChecker().check(payload)["candidate_status"])


if __name__ == "__main__":
    unittest.main()
