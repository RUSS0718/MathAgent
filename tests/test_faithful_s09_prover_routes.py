"""AC23 route projections retain the ceiling of each existing producer."""

import unittest

from showcase.prover_routes import prover_route_projection


class ProverRouteProjectionTest(unittest.TestCase):
    def test_existing_model_tool_and_formal_records_keep_grade_and_lineage(self):
        state = {
            "run_id": "run-1",
            "status": "completed_llm_reviewed",
            "calls": {
                "draft": {
                    "run_id": "run-1", "role": "reasoner", "status": "completed",
                    "request": {"prompt": "private"}, "usage": {"total_tokens": 10},
                    "requested_model": "Intern-S2",
                },
                "review": {
                    "run_id": "run-1", "role": "whole_solution_verifier",
                    "status": "completed", "response": {"verdict": "ACCEPT"},
                    "usage": {"total_tokens": 5},
                },
                "unknown": {
                    "run_id": "run-1", "role": "explore", "status": "unknown_outcome",
                    "request": {"prompt": "private"}, "usage": None,
                },
            },
            "tool_receipts": [
                {
                    "run_id": "run-1", "receipt_id": "poly-1", "tool": "polynomial_check",
                    "status": "success", "executed": True, "output_available": True,
                    "output": {"candidate_status": "pass"},
                    "attempt_index": 0, "step_id": "step", "claim_index": 0,
                },
                {
                    "run_id": "run-1", "receipt_id": "python-1", "tool": "python_math",
                    "status": "success", "executed": True, "output_available": True,
                    "output": "True", "comparison_status": "mismatched",
                    "attempt_index": 0, "step_id": "step", "claim_index": 1,
                },
                {
                    "run_id": "run-1", "receipt_id": "timeout-1", "tool": "python_math",
                    "status": "timeout", "executed": False, "unknown_outcome": True,
                    "attempt_index": 0, "step_id": "step", "claim_index": 2,
                },
                {
                    "run_id": "run-1", "receipt_id": "unknown-1", "tool": "python_math",
                    "status": "unknown_outcome", "executed": True, "unknown_outcome": True,
                    "attempt_index": 0, "step_id": "step", "claim_index": 3,
                },
            ],
            "formal_verification": {"attempts": [
                {"backend": "lean_tactic_prover", "attempt_id": "lean-1",
                 "parent_attempt_id": None, "status": "unknown", "grade": None,
                 "maximum_grade": "L3", "selection_reason": "explicit_retry",
                 "environment_identity": {"image": "sha256:test"},
                 "input_format": "formal-request-v1", "output_format": "formal-attempt-v1",
                 "deterministic": True, "unavailable_reason": "formal_environment_drift",
                 "cost": {"unknown": True}, "lineage": {"attempt_id": "lean-1"}},
            ]},
        }

        routes = prover_route_projection(state)
        drafts = [route for route in routes if route["backend_id"] == "llm_prover"
                  and route["target_type"] == "natural_language_draft"]
        reviewed = next(route for route in routes
                        if route["target_type"] == "natural_language_review")
        polynomial = next(route for route in routes
                          if route["backend_id"] == "math_tool_backend"
                          and route["tool"] == "polynomial_check")
        python_math = next(route for route in routes
                           if route["backend_id"] == "math_tool_backend"
                           and route["tool"] == "python_math")
        timeout = next(route for route in routes if route.get("tool") == "python_math"
                       and route["status"] == "timeout")
        unknown = next(route for route in routes if route.get("tool") == "python_math"
                       and route["status"] == "unknown")
        lean = next(route for route in routes if route["backend_id"] == "lean_tactic_prover")

        self.assertEqual("LLM_REVIEWED", reviewed["grade"])
        self.assertEqual("LLM_REVIEWED", reviewed["maximum_grade"])
        self.assertEqual("unknown", next(route for route in drafts
                                           if route["status"] == "unknown")["status"])
        self.assertEqual("L1", polynomial["grade"])
        self.assertEqual("L1", polynomial["maximum_grade"])
        self.assertIn("duration_seconds", polynomial["cost"])
        self.assertEqual(1, polynomial["lineage"]["sequence"])
        self.assertIsNone(python_math["grade"])
        self.assertEqual("L1", python_math["maximum_grade"])
        self.assertIsNone(timeout["grade"])
        self.assertTrue(timeout["unknown_outcome"])
        self.assertIsNone(unknown["grade"])
        self.assertEqual("unknown", lean["status"])
        self.assertIsNone(lean["grade"])
        self.assertEqual("L3", lean["maximum_grade"])
        self.assertEqual("formal_environment_drift", lean["unavailable_reason"])
        self.assertNotIn("private", repr(routes))

    def test_unregistered_or_unbound_sources_are_omitted(self):
        self.assertEqual([], prover_route_projection({"run_id": "run-1", "calls": {},
                                                      "tool_receipts": [],
                                                      "formal_verification": {"attempts": []}}))
        self.assertEqual([], prover_route_projection({"calls": {"call": {"role": "reasoner"}}}))


if __name__ == "__main__":
    unittest.main()
