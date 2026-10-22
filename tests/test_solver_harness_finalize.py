"""Final generation and independent whole-solution review public contracts."""

import unittest

from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort, SolverHarness

PLAN = {"version": 1, "steps": [{"step_id": "s1", "title": "derive", "objective": "bound"}]}
ACCEPT = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT"}
CONFIG = {
    "max_model_calls": 12,
    "features": {"final_generation": True, "final_solution_review": True},
}


class FinalizeTest(unittest.TestCase):
    def test_reject_then_accept_uses_fresh_review_and_persists_attempts(self):
        model = ScriptedModelPort(
            [
                {"argument": "valid bound"},
                {"final_response": "first"},
                {"final_response": "corrected"},
            ]
        )
        verifier = ScriptedVerifierPort(
            [ACCEPT, {"verdict": "REJECT", "reason": "missing boundary"}, {"verdict": "ACCEPT"}]
        )
        with SolverHarness(model_port=model, verifier_port=verifier, config=CONFIG) as harness:
            result = harness.solve("prove", {"run_id": "final", "plan": PLAN})
            self.assertEqual(result, harness.get_run("final"))
        self.assertEqual("completed_llm_reviewed", result["state"]["status"])
        self.assertEqual("corrected", result["state"]["final_response"])
        self.assertEqual(2, len(result["state"]["final_solution_attempts"]))
        self.assertNotEqual(
            verifier.requests[1]["session_key"], verifier.requests[2]["session_key"]
        )
        self.assertEqual("missing boundary", model.requests[2]["previous_review"]["reason"])

    def test_explore_plan_step_final_runs_without_supplied_plan(self):
        model = ScriptedModelPort(
            [
                {"assessment": "NEED_PLAN"},
                PLAN,
                {"argument": "valid bound"},
                {"final_response": "answer"},
            ]
        )
        verifier = ScriptedVerifierPort([ACCEPT, {"verdict": "ACCEPT"}])
        with SolverHarness(model_port=model, verifier_port=verifier, config=CONFIG) as harness:
            state = harness.solve("prove")["state"]
        self.assertEqual("completed_llm_reviewed", state["status"])
        self.assertEqual(
            ["explore", "planner", "reasoner", "final_generator"],
            [r["role"] for r in model.requests],
        )

    def test_reject_exhaustion_never_becomes_accepted(self):
        model = ScriptedModelPort(
            [{"argument": "valid"}, {"final_response": "bad"}]
            + [{"final_response": "bad again"}] * 2
        )
        verifier = ScriptedVerifierPort([ACCEPT] + [{"verdict": "REJECT", "reason": "gap"}] * 3)
        with SolverHarness(model_port=model, verifier_port=verifier, config=CONFIG) as harness:
            state = harness.solve("prove", {"plan": PLAN})["state"]
        self.assertEqual("partial_aborted", state["status"])
        self.assertEqual("final_review_retries_exhausted", state["finalization_reason"])
        self.assertEqual(3, len(state["final_solution_attempts"]))
        self.assertTrue(
            all(a["review"]["verdict"] == "REJECT" for a in state["final_solution_attempts"])
        )

    def test_budget_before_final_generation_dispatches_nothing_extra(self):
        for budget in (0, 2):
            model = ScriptedModelPort([{"argument": "valid"}, {"final_response": "answer"}])
            verifier = ScriptedVerifierPort([ACCEPT, {"verdict": "ACCEPT"}])
            with SolverHarness(
                model_port=model,
                verifier_port=verifier,
                config={**CONFIG, "max_model_calls": budget},
            ) as harness:
                state = harness.solve("prove", {"plan": PLAN})["state"]
            self.assertEqual("partial_budget_exhausted", state["status"])
            self.assertEqual(0 if budget == 0 else 1, len(model.requests))
            self.assertEqual(0 if budget == 0 else 1, len(verifier.requests))

    def test_failed_final_verifier_preserves_candidate_as_unverified(self):
        class FailingFinalVerifier:
            def __init__(self):
                self.count = 0

            def verify(self, request):
                self.count += 1
                if self.count == 1:
                    return ACCEPT
                raise RuntimeError("unavailable")

        with SolverHarness(
            model_port=ScriptedModelPort([{"argument": "valid"}, {"final_response": "candidate"}]),
            verifier_port=FailingFinalVerifier(),
            config=CONFIG,
        ) as harness:
            state = harness.solve("prove", {"plan": PLAN})["state"]
        self.assertEqual("completed_unverified", state["status"])
        self.assertEqual("candidate", state["final_response"])
        self.assertEqual("final_verifier_failed", state["finalization_reason"])

    def test_absent_final_verifier_and_invalid_fact_filter_at_recovery(self):
        from showcase.storage import SQLiteStore

        store = SQLiteStore(":memory:")
        with SolverHarness(store=store, config=CONFIG) as seed:
            run = seed.solve("prove", {"run_id": "recover"})
            seed.commit_event(
                "recover",
                expected_revision=run["state_revision"],
                event={"event_id": "accepted", "type": "accepted"},
                state_updates={
                    "phase": "FINAL_GENERATE",
                    "plan": PLAN,
                    "plan_version": 1,
                    "steps": {"s1": {"verification": {**ACCEPT, "valid": True}}},
                    "accepted_results": [
                        {
                            "source": "s1",
                            "statement": "safe",
                            "dependencies": [],
                            "evidence_level": "llm_reviewed",
                        },
                        {
                            "source": "s1",
                            "statement": "stale",
                            "dependencies": [],
                            "evidence_level": "llm_reviewed",
                            "invalidated": True,
                        },
                        {
                            "source": "s1",
                            "statement": "unknown",
                            "dependencies": ["missing"],
                            "evidence_level": "llm_reviewed",
                        },
                    ],
                },
            )
        model = ScriptedModelPort([{"final_response": "candidate"}])
        with SolverHarness(store=store, config=CONFIG, model_port=model) as harness:
            result = harness.solve("prove", {"run_id": "recover"})
            self.assertEqual(result, harness.get_run("recover"))
        self.assertEqual("completed_unverified", result["state"]["status"])
        self.assertEqual("final_verifier_unavailable", result["state"]["finalization_reason"])
        self.assertEqual(["safe"], [f["statement"] for f in model.requests[0]["accepted_results"]])
