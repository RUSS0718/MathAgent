"""Whole-solution review through public Harness operations."""

import tempfile
import unittest
from pathlib import Path

from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort, SolverHarness


class SolverHarnessReviewTest(unittest.TestCase):
    def test_accept_completes_without_plan_and_survives_recovery(self):
        model = ScriptedModelPort([{"assessment": "SOLVED", "solution_candidate": "2"}])
        verifier = ScriptedVerifierPort([{"verdict": "ACCEPT"}])
        with SolverHarness(model_port=model, verifier_port=verifier) as harness:
            result = harness.solve("1 + 1", {"run_id": "accepted"})
            self.assertEqual(result, harness.get_run("accepted"))
            self.assertEqual(result, harness.solve("1 + 1", {"run_id": "accepted"}))
        self.assertEqual("completed_llm_reviewed", result["state"]["status"])
        self.assertEqual("2", result["state"]["final_response"])
        self.assertNotIn("PLAN", [event.get("next_phase") for event in result["events"]])
        self.assertEqual(1, len(model.requests))
        self.assertEqual(1, len(verifier.requests))
        self.assertEqual(2, result["state"]["counters"]["model_calls"])
        self.assertEqual("2", verifier.requests[0]["solution_candidate"])

    def test_reviewed_state_and_events_survive_new_harness(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "solver.sqlite3"
            with SolverHarness(
                database_path=database,
                model_port=ScriptedModelPort([{"assessment": "SOLVED", "solution_candidate": "2"}]),
                verifier_port=ScriptedVerifierPort([{"verdict": "ACCEPT"}]),
            ) as harness:
                result = harness.solve("1 + 1", {"run_id": "recover-reviewed"})
            with SolverHarness(database_path=database) as recovered:
                self.assertEqual(result, recovered.get_run("recover-reviewed"))
                self.assertEqual(result, recovered.solve("1 + 1", {"run_id": "recover-reviewed"}))
            for field in ("candidate_registry", "best_effort_decision", "finalization_reason"):
                self.assertIsNone(result["state"][field])

    def test_default_initialization_dispatches_no_calls(self):
        verifier = ScriptedVerifierPort([{"verdict": "ACCEPT"}])
        with SolverHarness(verifier_port=verifier) as harness:
            result = harness.solve("1 + 1")
        self.assertEqual({"model_calls": 0, "tool_calls": 0}, result["state"]["counters"])
        self.assertEqual([], verifier.requests)
        for field in ("candidate_registry", "best_effort_decision", "finalization_reason"):
            self.assertIsNone(result["state"][field])

    def test_reject_preserves_findings_and_hands_off_to_plan(self):
        finding = {
            "assessment": "SOLVED",
            "solution_candidate": "3",
            "worked": ["a pattern"],
            "failed": ["boundary"],
        }
        model = ScriptedModelPort([finding])
        verifier = ScriptedVerifierPort([{"verdict": "REJECT"}])
        with SolverHarness(model_port=model, verifier_port=verifier) as harness:
            result = harness.solve("1 + 1", {"run_id": "rejected"})
            self.assertEqual(result, harness.get_run("rejected"))
        self.assertEqual("PLAN", result["state"]["phase"])
        self.assertEqual("running", result["state"]["status"])
        self.assertEqual("3", result["state"]["exploration_findings"][0]["solution_candidate"])
        self.assertEqual(["a pattern"], result["state"]["exploration_findings"][0]["worked"])
        self.assertEqual(["boundary"], result["state"]["exploration_findings"][0]["failed"])
        self.assertEqual([], result["state"]["accepted_results"])
        self.assertEqual(1, len(verifier.requests))

    def test_extensions_stay_none_without_added_calls(self):
        model = ScriptedModelPort([{"assessment": "NEED_PLAN"}])
        verifier = ScriptedVerifierPort([{"verdict": "ACCEPT"}])
        with SolverHarness(model_port=model, verifier_port=verifier) as harness:
            result = harness.solve("1 + 1")
        for field in ("candidate_registry", "best_effort_decision", "finalization_reason"):
            self.assertIsNone(result["state"][field])
        self.assertEqual(1, len(model.requests))
        self.assertEqual([], verifier.requests)
        self.assertEqual(0, result["state"]["counters"]["tool_calls"])

    def test_review_budget_exhaustion_adds_no_verifier_call(self):
        import json

        model = ScriptedModelPort([{"assessment": "SOLVED", "solution_candidate": "2"}])
        verifier = ScriptedVerifierPort([{"verdict": "ACCEPT"}])
        with SolverHarness(
            model_port=model, verifier_port=verifier, config={"max_model_calls": 1}
        ) as harness:
            result = harness.solve("1 + 1")
        self.assertEqual([], verifier.requests)
        self.assertEqual(1, len(model.requests))
        self.assertEqual("partial_budget_exhausted", result["state"]["status"])
        self.assertTrue(result["state"]["final_response"])
        self.assertEqual(1, result["state"]["counters"]["model_calls"])
        self.assertIsNone(result["state"]["finalization_reason"])
        json.dumps(result, allow_nan=False)

    def test_verifier_exception_returns_safe_runtime_failure(self):
        class FailingVerifier:
            def verify(self, request):
                raise RuntimeError("SECRET_PROMPT_AND_CREDENTIAL")

        with SolverHarness(
            model_port=ScriptedModelPort([{"assessment": "SOLVED", "solution_candidate": "2"}]),
            verifier_port=FailingVerifier(),
        ) as harness:
            result = harness.solve("1 + 1")
            self.assertEqual(result, harness.get_run(result["run_id"]))
        self.assertEqual("failed_runtime", result["state"]["status"])
        self.assertEqual("TERMINAL", result["state"]["phase"])
        self.assertTrue(result["state"]["final_response"])
        self.assertNotIn("SECRET_PROMPT_AND_CREDENTIAL", repr(result))
        self.assertEqual(2, result["state"]["counters"]["model_calls"])

    def test_invalid_verdict_or_empty_candidate_cannot_complete(self):
        for verdict, candidate in [("UNKNOWN", "2"), (["ACCEPT"], "2"), ("ACCEPT", " ")]:
            with self.subTest(verdict=verdict, candidate=candidate):
                with SolverHarness(
                    model_port=ScriptedModelPort(
                        [{"assessment": "SOLVED", "solution_candidate": candidate}]
                    ),
                    verifier_port=ScriptedVerifierPort([{"verdict": verdict}]),
                ) as harness:
                    result = harness.solve("1 + 1")
                self.assertEqual("PLAN", result["state"]["phase"])
                self.assertNotEqual("completed_llm_reviewed", result["state"]["status"])


if __name__ == "__main__":
    unittest.main()
