"""Qualitative evidence grades through public candidate review transitions."""

import unittest

from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort, SolverHarness


class EvidenceGradeTest(unittest.TestCase):
    def test_whole_review_without_independent_evidence_is_medium_not_probability(self):
        model = ScriptedModelPort(
            [
                {
                    "assessment": "SOLVED",
                    "solution_candidate": "42",
                    "confidence": 0.99,
                    "independently_verified": True,
                }
            ]
        )
        with SolverHarness(
            config={"features": {"candidate_registry": True}},
            model_port=model,
            verifier_port=ScriptedVerifierPort([{"verdict": "ACCEPT", "confidence": 0.99}]),
        ) as harness:
            result = harness.solve("compute", {"run_id": "grades"})
            self.assertEqual(result, harness.get_run("grades"))
        records = result["state"]["candidate_registry"]
        self.assertEqual("low", records[0]["evidence_grade"]["confidence_level"])
        grade = records[-1]["evidence_grade"]
        self.assertEqual("medium", grade["confidence_level"])
        self.assertIn("missing_independent_support", grade["reason_codes"])
        self.assertEqual(
            ["missing:independent_support"], grade["reason_evidence"]["missing_independent_support"]
        )
        self.assertNotIn("probability", grade)

    def test_whole_review_and_executed_applicable_computation_can_be_high_without_formal_claim(
        self,
    ):
        from showcase.solver_harness.tool_ports import RegistryToolPort
        from showcase.tools import ToolRegistry

        registry = ToolRegistry()
        registry.register("polynomial_check", lambda args: {"value": sum(args["numbers"])})
        model = ScriptedModelPort(
            [
                {
                    "argument": "2+2=4",
                    "claims": [
                        {
                            "statement": "2+2=4",
                            "label": "easy-verify",
                            "tool_request": {
                                "tool": "polynomial_check",
                                "arguments": {"numbers": [2, 2]},
                                "scope": "finite_computation",
                                "expected_output": {"value": 4},
                            },
                        }
                    ],
                },
                {"final_response": "4"},
            ]
        )
        verifier = ScriptedVerifierPort(
            [{"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT"}, {"verdict": "ACCEPT"}]
        )
        config = {
            "max_model_calls": 4,
            "allowed_tools": ["polynomial_check"],
            "features": {
                "candidate_registry": True,
                "local_code_tool": True,
                "final_generation": True,
                "final_solution_review": True,
            },
        }
        plan = {
            "version": 1,
            "steps": [{"step_id": "s1", "title": "sum", "objective": "compute 2+2"}],
        }
        with SolverHarness(
            config=config,
            model_port=model,
            verifier_port=verifier,
            tool_port=RegistryToolPort(registry),
        ) as harness:
            result = harness.solve("compute 2+2", {"run_id": "executed", "plan": plan})
            self.assertEqual(result, harness.get_run("executed"))
        grade = result["state"]["candidate_registry"][-1]["evidence_grade"]
        self.assertEqual("high", grade["confidence_level"])
        self.assertEqual([], grade["unresolved_questions"])
        self.assertEqual(
            [result["state"]["tool_receipts"][0]["receipt_id"]], grade["independent_evidence_refs"]
        )
        self.assertEqual("heuristic_review_and_finite_computation", grade["evidence_scope"])
        self.assertNotIn("formally_proved", str(grade))
