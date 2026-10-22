"""Bounded challenge behavior through the public Harness seam."""

import unittest

from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort, SolverHarness

PLAN = {"version": 1, "steps": [{"step_id": "s1", "title": "求值", "objective": "证明"}]}
ACCEPT = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT"}
CHALLENGE = {
    "goal_gate": "PARTIAL",
    "logic_gate": "UNCERTAIN",
    "verdict": "CHALLENGE",
    "objection": "Explain the boundary case",
}


class ChallengeTest(unittest.TestCase):
    def test_three_objections_are_answered_in_one_session_before_accept(self):
        model = ScriptedModelPort([{"argument": str(i)} for i in range(4)])
        verifier = ScriptedVerifierPort([CHALLENGE] * 3 + [ACCEPT])
        with SolverHarness(
            model_port=model, verifier_port=verifier, config={"max_model_calls": 8}
        ) as harness:
            result = harness.solve("prove", {"run_id": "rounds", "plan": PLAN})
            self.assertEqual(result, harness.get_run("rounds"))
        state = result["state"]
        self.assertEqual("FINAL_GENERATE", state["phase"])
        self.assertEqual(1, len(state["accepted_results"]))
        history = state["steps"]["s1"]["challenge_history"]
        self.assertEqual([1, 2, 3], [item["round"] for item in history])
        self.assertEqual(
            ["CHALLENGE", "CHALLENGE", "ACCEPT"], [item["verdict"]["verdict"] for item in history]
        )
        self.assertEqual(
            {"verify:rounds:plan1:steps1"}, {r["session_key"] for r in verifier.requests}
        )
        self.assertEqual("Explain the boundary case", model.requests[1]["objection"])
        self.assertEqual("3", history[-1]["reasoner_reply"]["argument"])

    def test_cap_escalates_without_acceptance(self):
        with SolverHarness(
            model_port=ScriptedModelPort([{}] * 3),
            verifier_port=ScriptedVerifierPort([CHALLENGE] * 3),
            config={"max_model_calls": 6, "max_challenge_rounds": 2},
        ) as harness:
            state = harness.solve("prove", {"plan": PLAN})["state"]
        self.assertEqual("META_DECIDE", state["phase"])
        self.assertEqual("STALEMATE", state["steps"]["s1"]["status"])
        self.assertEqual([], state["accepted_results"])
        self.assertEqual(2, len(state["steps"]["s1"]["challenge_history"]))
        self.assertEqual("STALEMATE", state["meta_interventions"][0]["trigger"])

    def test_next_step_uses_distinct_session(self):
        plan = {
            "version": 1,
            "steps": [
                *PLAN["steps"],
                {"step_id": "s2", "title": "next", "objective": "substitute"},
            ],
        }
        verifier = ScriptedVerifierPort([ACCEPT, ACCEPT])
        with SolverHarness(
            model_port=ScriptedModelPort([{"argument": "a"}, {"argument": "b"}]),
            verifier_port=verifier,
            config={"max_model_calls": 4},
        ) as harness:
            state = harness.solve("prove", {"run_id": "sessions", "plan": plan})["state"]
        self.assertEqual("FINAL_GENERATE", state["phase"])
        self.assertEqual(
            ["verify:sessions:plan1:steps1", "verify:sessions:plan1:steps2"],
            [r["session_key"] for r in verifier.requests],
        )

    def test_budget_is_checked_before_each_challenge_dispatch(self):
        for budget, model_calls, verifier_calls, phase in [
            (2, 1, 1, "CHALLENGE"),
            (3, 2, 1, "TERMINAL"),
        ]:
            with self.subTest(budget=budget):
                model = ScriptedModelPort([{"argument": "initial"}, {"argument": "reply"}])
                verifier = ScriptedVerifierPort([CHALLENGE, ACCEPT])
                with SolverHarness(
                    model_port=model, verifier_port=verifier, config={"max_model_calls": budget}
                ) as harness:
                    state = harness.solve("prove", {"plan": PLAN})["state"]
                self.assertEqual(model_calls, len(model.requests))
                self.assertEqual(verifier_calls, len(verifier.requests))
                self.assertEqual(phase, state["phase"])
                self.assertEqual([], state["accepted_results"])
                self.assertEqual(
                    "model_call_budget_exhausted", state["budget"]["exhaustion_reason"]
                )

    def test_continuing_challenge_never_exposes_accepted_result(self):
        snapshots = []

        class ObservedModel(ScriptedModelPort):
            def complete(self, request):
                if request.get("round"):
                    snapshots.append(harness.get_run(request["run_id"])["state"])
                return super().complete(request)

        with SolverHarness(
            model_port=ObservedModel([{"argument": "x"}] * 4),
            verifier_port=ScriptedVerifierPort([CHALLENGE] * 3 + [ACCEPT]),
            config={"max_model_calls": 8},
        ) as harness:
            result = harness.solve("prove", {"plan": PLAN})
        self.assertEqual(3, len(snapshots))
        for state in snapshots:
            self.assertEqual([], state["accepted_results"])
            self.assertNotEqual("ACCEPTED", state["steps"]["s1"]["status"])
        accepted = [
            event
            for event in result["events"]
            if event["type"] == "step_reviewed" and event.get("verdict") == "ACCEPT"
        ]
        self.assertEqual(1, len(accepted))
