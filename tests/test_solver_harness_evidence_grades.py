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
        from showcase.solver_harness.tool_ports import RegistryToolPort, ScriptedToolPort
        from showcase.tools import ToolRegistry

        registry = ToolRegistry()
        registry.register("polynomial_check", lambda args: {"value": sum(args["numbers"])})
        responses = [
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
        reviews = [
            {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT"},
            {"verdict": "ACCEPT"},
        ]
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
        ports = [
            (RegistryToolPort(registry), "high"),
            (
                ScriptedToolPort([{"status": "success", "output": {"value": 4}, "exit_code": 0}]),
                "medium",
            ),
        ]
        for port, expected in ports:
            with (
                self.subTest(source=port.source),
                SolverHarness(
                    config=config,
                    model_port=ScriptedModelPort(responses),
                    verifier_port=ScriptedVerifierPort(reviews),
                    tool_port=port,
                ) as harness,
            ):
                result = harness.solve("compute 2+2", {"run_id": "executed", "plan": plan})
                self.assertEqual(result, harness.get_run("executed"))
            grade = result["state"]["candidate_registry"][-1]["evidence_grade"]
            self.assertEqual(expected, grade["confidence_level"])
            if expected == "high":
                self.assertEqual([], grade["unresolved_questions"])
                self.assertEqual(
                    [result["state"]["tool_receipts"][0]["receipt_id"]],
                    grade["independent_evidence_refs"],
                )
            else:
                self.assertEqual([], grade["independent_evidence_refs"])
                self.assertIn("missing_independent_support", grade["reason_codes"])
            self.assertEqual("heuristic_review_and_finite_computation", grade["evidence_scope"])
            self.assertNotIn("formally_proved", str(grade))

    def test_refuted_candidate_stays_rejected_with_append_only_review_grades(self):
        with SolverHarness(
            config={"features": {"candidate_registry": True}},
            model_port=ScriptedModelPort([{"assessment": "SOLVED", "solution_candidate": "wrong"}]),
            verifier_port=ScriptedVerifierPort(
                [{"verdict": "REJECT", "counterexample": "x=0 contradicts the bound"}]
            ),
        ) as harness:
            result = harness.solve("prove", {"run_id": "refutation"})
            self.assertEqual(result, harness.get_run("refutation"))
        initial, refuted = result["state"]["candidate_registry"]
        self.assertEqual("low", initial["evidence_grade"]["confidence_level"])
        self.assertEqual("rejected", refuted["evidence_grade"]["confidence_level"])
        self.assertFalse(refuted["selection_eligible"])
        self.assertEqual(
            ["review-assessed"], refuted["evidence_grade"]["reason_evidence"]["decisively_refuted"]
        )
        self.assertEqual([1, 2], [initial["version"], refuted["version"]])

    def test_unknown_review_refs_and_self_verification_cannot_establish_high(self):
        from showcase.solver_harness.confidence import grade_candidate, verified_whole_review_refs

        record = {
            "candidate_id": "c",
            "run_id": "r",
            "problem_hash": "p",
            "source_phase": "EXPLORE",
            "source_event_refs": ["created", "made-up-review"],
            "evidence_refs": ["made-up-review"],
            "review_state": "whole_reviewed",
            "answer_text": "42",
            "answer_completeness": "complete",
            "independently_verified": True,
            "confidence": 0.99,
        }
        state = {"run_id": "r", "problem_hash": "p", "tool_receipts": []}
        events = [{"event_id": "created", "type": "explore_assessed", "run_id": "r"}]
        grade = grade_candidate(record, state, events=events)
        self.assertEqual([], verified_whole_review_refs(record, state, events))
        self.assertEqual("low", grade["confidence_level"])
        self.assertNotIn("made-up-review", grade["evidence_refs"])
        self.assertEqual(
            ["missing:accepted_review"], grade["reason_evidence"]["missing_key_review"]
        )
