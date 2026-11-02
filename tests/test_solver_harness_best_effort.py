import unittest

from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort, SolverHarness


def candidate(cid, text, review="eligible_unreviewed", **extra):
    return {
        "candidate_id": cid,
        "source_phase": "EXPLORE",
        "plan_version": 0,
        "attempt_index": 0,
        "source_event_refs": [],
        "step_refs": [],
        "version": 1,
        "answer_text": text,
        "answer_hash": cid,
        "answer_completeness": "complete",
        "review_state": review,
        "selection_eligible": True,
        "evidence_refs": [],
        "dependency_refs": [],
        "known_objections": [],
        "invalidated_by": [],
        **extra,
    }


class BestEffortTest(unittest.TestCase):
    def test_recovery_selects_persisted_candidate_with_zero_additional_calls(self):
        model, verifier = ScriptedModelPort([]), ScriptedVerifierPort([])
        config = {"max_model_calls": 3, "features": {"best_effort": True, "stream_recovery": True}}
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "runs.db"
            with SolverHarness(config=config, database_path=database) as seed:
                run = seed.solve("prove", {"run_id": "select"})
                run = seed.commit_event(
                    "select",
                    expected_revision=run["state_revision"],
                    event={"event_id": "seed-candidates", "type": "seed_candidates"},
                    state_updates={
                        "candidate_registry": [
                            candidate("a-unreviewed", "weak"),
                        ]
                    },
                )
                run = seed.commit_event(
                    "select",
                    expected_revision=run["state_revision"],
                    event={"event_id": "explore-source", "type": "explore_assessed"},
                    state_updates={
                        "phase": "EXPLORE_REVIEW",
                        "exploration_findings": [
                            {"assessment": "SOLVED", "solution_candidate": "strong"}
                        ],
                    },
                )
                run = seed.commit_event(
                    "select",
                    expected_revision=run["state_revision"],
                    event={
                        "event_id": "accepted-review",
                        "type": "solution_review_assessed",
                        "verdict": "ACCEPT",
                    },
                )
                seed.commit_event(
                    "select",
                    expected_revision=run["state_revision"],
                    event={"event_id": "budget", "type": "budget_exhausted"},
                    state_updates={
                        "phase": "TERMINAL",
                        "status": "partial_budget_exhausted",
                        "counters": {"model_calls": 3, "tool_calls": 0},
                        "budget": {"exhaustion_reason": "model_call_budget_exhausted"},
                    },
                )
            with SolverHarness(
                config=config, database_path=database, model_port=model, verifier_port=verifier
            ) as harness:
                result = harness.get_run("select")
                self.assertEqual("strong", result["state"]["final_response"])
                self.assertEqual(result, harness.solve("prove", {"run_id": "select"}))
        self.assertEqual(
            "select:candidate:explore-source",
            result["state"]["best_effort_decision"]["selected_candidate_id"],
        )
        self.assertEqual("partial_budget_exhausted", result["state"]["status"])
        self.assertEqual([], model.requests)
        self.assertEqual([], verifier.requests)

    def test_zero_budget_without_candidate_returns_explicit_unsolved(self):
        model = ScriptedModelPort([])
        with SolverHarness(
            model_port=model, config={"max_model_calls": 0, "features": {"best_effort": True}}
        ) as harness:
            state = harness.solve("prove")["state"]
        self.assertEqual("no_eligible_candidate", state["best_effort_decision"]["status"])
        self.assertTrue(state["final_response"].strip())
        self.assertEqual([], model.requests)

    def test_actual_explore_budget_selects_answer_without_review_dispatch(self):
        model = ScriptedModelPort(
            [{"assessment": "SOLVED", "solution_candidate": "persisted answer"}]
        )
        verifier = ScriptedVerifierPort([{"verdict": "ACCEPT"}])
        with SolverHarness(
            model_port=model,
            verifier_port=verifier,
            config={
                "max_model_calls": 1,
                "features": {"best_effort": True, "stream_recovery": True},
            },
        ) as harness:
            result = harness.solve("prove", {"run_id": "actual"})
            self.assertEqual(result, harness.get_run("actual"))
        self.assertEqual("persisted answer", result["state"]["final_response"])
        self.assertEqual(1, len(model.requests))
        self.assertEqual([], verifier.requests)
        self.assertEqual(1, result["state"]["counters"]["model_calls"])

    def test_invalid_candidates_are_excluded_and_ties_are_stable(self):
        config = {"max_model_calls": 1, "features": {"best_effort": True, "stream_recovery": True}}
        records = [
            candidate("z", "alternative"),
            candidate("a", "chosen"),
            candidate("blank", " "),
            candidate("partial", "fragment", answer_completeness="partial"),
            candidate("refuted", "wrong", "refuted"),
            candidate("invalidated", "old", "invalidated"),
            candidate("dependency", "unknown", dependency_refs=["missing"]),
        ]
        with SolverHarness(config=config) as harness:
            run = harness.solve("prove", {"run_id": "ties"})
            harness.commit_event(
                "ties",
                expected_revision=run["state_revision"],
                event={"event_id": "budget", "type": "budget_exhausted"},
                state_updates={
                    "status": "partial_budget_exhausted",
                    "phase": "TERMINAL",
                    "counters": {"model_calls": 1, "tool_calls": 0},
                    "candidate_registry": records,
                },
            )
            first = harness.get_run("ties")
            second = harness.get_run("ties")
            self.assertEqual(first, second)
            with self.assertRaises(ValueError):
                harness.commit_event(
                    "ties",
                    expected_revision=first["state_revision"],
                    event={"event_id": "backdoor", "type": "best_effort_selected"},
                    state_updates={"final_response": "forged"},
                )
        decision = first["state"]["best_effort_decision"]
        self.assertEqual("a", decision["selected_candidate_id"])
        self.assertIn("candidate_conflict", decision["reason_codes"])
        self.assertEqual("low", decision["confidence_level"])
        self.assertEqual(
            ["blank", "dependency", "invalidated", "partial", "refuted"],
            decision["excluded_candidate_ids"],
        )

    def test_disabled_feature_keeps_optional_fields_none(self):
        with SolverHarness(config={"max_model_calls": 0}) as harness:
            state = harness.solve("prove")["state"]
        self.assertIsNone(state["best_effort_decision"])
        self.assertIsNone(state["finalization_reason"])

    def test_persisted_hard_stop_does_not_dispatch_meta_even_with_model_allowance(self):
        from showcase.storage import SQLiteStore

        store = SQLiteStore(":memory:")
        config = {"max_model_calls": 5, "features": {"best_effort": True}}
        with SolverHarness(store=store, config=config) as seed:
            run = seed.solve("prove", {"run_id": "stop"})
            seed.commit_event(
                "stop",
                expected_revision=run["state_revision"],
                event={"event_id": "tool-budget", "type": "budget_exhausted"},
                state_updates={
                    "phase": "META_DECIDE",
                    "status": "partial_budget_exhausted",
                    "budget": {"exhaustion_reason": "tool_call_budget_exhausted"},
                },
            )
        meta = ScriptedModelPort([])
        with SolverHarness(store=store, config=config, meta_port=meta) as harness:
            result = harness.solve("prove", {"run_id": "stop", "meta_trigger": "plan-blocked"})
        self.assertEqual([], meta.requests)
        self.assertEqual("tool_call_budget_exhausted", result["state"]["finalization_reason"])
