"""Strict supplied plans and step verdicts at solve/get_run seams."""

import unittest

from showcase.solver_harness import (
    ScriptedModelPort,
    ScriptedVerifierPort,
    SolverHarness,
    SolverValidationError,
)


class SolverHarnessVerificationTest(unittest.TestCase):
    def test_invalid_plan_never_dispatches(self):
        invalid = [
            None,
            {},
            {"version": True, "steps": []},
            {"version": 0, "steps": [{"step_id": "s1", "title": "步骤一", "objective": "x"}]},
            {"version": 1, "steps": []},
            {"version": 1, "steps": [{"step_id": "", "title": "步骤", "objective": "x"}]},
            {"version": 1, "steps": [{"step_id": "s1", "title": "步骤一", "objective": " "}]},
            {
                "version": 1,
                "steps": [
                    {"step_id": "s1", "title": "步骤一", "objective": "x", "depends_on": ["s2"]},
                    {"step_id": "s2", "title": "步骤二", "objective": "y"},
                ],
            },
            {"version": 1, "steps": [{"step_id": "s1", "title": "步骤一", "objective": "x"}] * 2},
            {
                "version": 1,
                "steps": [
                    {"step_id": f"s{i}", "title": "步骤", "objective": "x"} for i in range(21)
                ],
            },
        ]
        for plan in invalid:
            with self.subTest(plan=plan):
                model = ScriptedModelPort([])
                verifier = ScriptedVerifierPort([])
                with SolverHarness(model_port=model, verifier_port=verifier) as harness:
                    with self.assertRaises(SolverValidationError):
                        harness.solve("problem", {"plan": plan})
                self.assertEqual([], model.requests)
                self.assertEqual([], verifier.requests)

    def test_only_strict_double_gate_accept_advances_and_persists_evidence(self):
        verdicts = [
            ({"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT"}, True),
            ({"goal_gate": "NO", "logic_gate": "PASS", "verdict": "ACCEPT"}, False),
            ({"goal_gate": "PARTIAL", "logic_gate": "PASS", "verdict": "ACCEPT"}, False),
            ({"goal_gate": "YES", "logic_gate": "UNCERTAIN", "verdict": "ACCEPT"}, False),
            ({"goal_gate": "YES", "logic_gate": "FAIL", "verdict": "ACCEPT"}, False),
            ({"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT or CHALLENGE"}, False),
            ({"verdict": "ACCEPT"}, False),
        ]
        for reply, accepted in verdicts:
            with self.subTest(reply=reply):
                plan = {
                    "version": 1,
                    "steps": [
                        {"step_id": "s1", "title": "步骤一", "objective": "求值"},
                        {
                            "step_id": "s2",
                            "title": "步骤二",
                            "objective": "代入",
                            "depends_on": ["s1"],
                        },
                    ],
                }
                model = ScriptedModelPort([{"argument": "2²=4", "claims": ["2²=4"]}])
                verifier = ScriptedVerifierPort([reply])
                with SolverHarness(model_port=model, verifier_port=verifier) as harness:
                    result = harness.solve("计算", {"run_id": "gates", "plan": plan})
                    self.assertEqual(result, harness.get_run("gates"))
                    self.assertEqual(
                        result, harness.solve("计算", {"run_id": "gates", "plan": plan})
                    )
                state = result["state"]
                self.assertEqual("running", state["status"])
                self.assertIsNone(state["finalization_reason"])
                self.assertEqual("s2" if accepted else "s1", state["current_step"])
                self.assertEqual(
                    "ACCEPTED" if accepted else "VERIFYING", state["steps"]["s1"]["status"]
                )
                self.assertEqual(accepted, state["steps"]["s1"]["verification"]["valid"])
                self.assertEqual(1, len(verifier.requests))
                self.assertEqual("step_verifier", verifier.requests[0]["role"])
                self.assertEqual(2, state["counters"]["model_calls"])
                if accepted:
                    evidence = state["accepted_results"][0]
                    self.assertEqual("2²=4", evidence["statement"])
                    self.assertEqual("llm_reviewed", evidence["evidence_level"])
                    self.assertEqual("s1", evidence["source"])
                    self.assertEqual([], evidence["dependencies"])
                    self.assertEqual("step_result", evidence["category"])
                else:
                    self.assertEqual([], state["accepted_results"])

    def test_nonaccept_routes_only_valid_verdicts(self):
        for verdict, target, expected in [
            ("CHALLENGE", None, "CHALLENGE"),
            ("PROPOSE_REPLAN", None, "META_DECIDE"),
            ("TRACE_BACK", 1, "TRACE_BACK"),
            ("TRACE_BACK", 0, "STEP_VERIFY"),
            ("TRACE_BACK", 2, "STEP_VERIFY"),
            ("TRACE_BACK", True, "STEP_VERIFY"),
            ("TRACE_BACK", None, "STEP_VERIFY"),
        ]:
            with self.subTest(verdict=verdict, target=target):
                verifier = ScriptedVerifierPort(
                    [
                        {
                            "goal_gate": "NO",
                            "logic_gate": "FAIL",
                            "verdict": verdict,
                            "trace_back_to": target,
                        }
                    ]
                )
                with SolverHarness(
                    model_port=ScriptedModelPort([{}]), verifier_port=verifier
                ) as harness:
                    result = harness.solve(
                        "x",
                        {
                            "plan": {
                                "version": 1,
                                "steps": [{"step_id": "a", "title": "步骤", "objective": "x"}],
                            }
                        },
                    )
                self.assertEqual(expected, result["state"]["phase"])
                self.assertEqual([], result["state"]["accepted_results"])
                self.assertEqual("a", result["state"]["current_step"])

    def test_last_step_accept_waits_for_whole_solution_review(self):
        with SolverHarness(
            model_port=ScriptedModelPort([{"argument": "result"}]),
            verifier_port=ScriptedVerifierPort(
                [{"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT"}]
            ),
        ) as harness:
            result = harness.solve(
                "x",
                {
                    "plan": {
                        "version": 1,
                        "steps": [{"step_id": "a", "title": "步骤", "objective": "x"}],
                    }
                },
            )
        self.assertEqual("FINAL_GENERATE", result["state"]["phase"])
        self.assertEqual("running", result["state"]["status"])
        self.assertIsNone(result["state"]["current_step"])
        self.assertIsNone(result["state"]["finalization_reason"])

    def test_review_budget_and_runtime_failure_never_accept(self):
        class BrokenVerifier:
            def verify(self, request):
                raise RuntimeError("verifier failed")

        for budget, verifier, expected in [
            (1, ScriptedVerifierPort([]), "TERMINAL"),
            (2, BrokenVerifier(), "STEP_VERIFY"),
        ]:
            with self.subTest(budget=budget):
                with SolverHarness(
                    model_port=ScriptedModelPort([{}]),
                    verifier_port=verifier,
                    config={"max_model_calls": budget},
                ) as harness:
                    result = harness.solve(
                        "x",
                        {
                            "plan": {
                                "version": 1,
                                "steps": [{"step_id": "a", "title": "步骤", "objective": "x"}],
                            }
                        },
                    )
                self.assertEqual(expected, result["state"]["phase"])
                self.assertEqual([], result["state"]["accepted_results"])
                self.assertEqual("VERIFYING", result["state"]["steps"]["a"]["status"])
                self.assertIsNone(result["state"]["finalization_reason"])

    def test_malformed_verifier_response_is_persisted_as_invalid(self):
        class RawVerifier:
            def __init__(self, reply):
                self.reply = reply

            def verify(self, request):
                return self.reply

        for reply in [
            None,
            "## Verdict\\nACCEPT",
            {"goal_gate": ["YES"], "logic_gate": "PASS", "verdict": "ACCEPT"},
            {"goal_gate": "YES", "logic_gate": "PASS", "verdict": ["ACCEPT"]},
        ]:
            with self.subTest(reply=reply):
                with SolverHarness(
                    model_port=ScriptedModelPort([{}]), verifier_port=RawVerifier(reply)
                ) as harness:
                    result = harness.solve(
                        "x",
                        {
                            "plan": {
                                "version": 1,
                                "steps": [{"step_id": "a", "title": "步骤", "objective": "x"}],
                            }
                        },
                    )
                self.assertEqual("STEP_VERIFY", result["state"]["phase"])
                self.assertFalse(result["state"]["steps"]["a"]["verification"]["valid"])
                self.assertEqual([], result["state"]["accepted_results"])

    def test_missing_or_blank_title_never_dispatches(self):
        for fields in ({}, {"title": ""}, {"title": "  "}, {"title": None}):
            with self.subTest(fields=fields):
                model = ScriptedModelPort([])
                verifier = ScriptedVerifierPort([])
                plan = {"version": 1, "steps": [{"step_id": "s1", "objective": "求值", **fields}]}
                with SolverHarness(model_port=model, verifier_port=verifier) as harness:
                    with self.assertRaisesRegex(SolverValidationError, "title"):
                        harness.solve("problem", {"plan": plan})
                self.assertEqual([], model.requests)
                self.assertEqual([], verifier.requests)
