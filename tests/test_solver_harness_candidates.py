import unittest

from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort, SolverHarness


class CandidateTest(unittest.TestCase):
    def test_explore_registration_keeps_exact_answer_and_review_history(self):
        port = ScriptedModelPort([{"assessment": "SOLVED", "solution_candidate": "  answer  "}])
        with SolverHarness(
            model_port=port,
            verifier_port=ScriptedVerifierPort([{"verdict": "ACCEPT"}]),
            config={"features": {"candidate_registry": True}},
        ) as harness:
            result = harness.solve("prove", {"run_id": "c"})
            self.assertEqual(result, harness.get_run("c"))
        records = result["state"]["candidate_registry"]
        self.assertEqual(2, len(records))
        self.assertEqual("  answer  ", records[0]["answer_text"])
        self.assertEqual("eligible_unreviewed", records[0]["review_state"])
        self.assertEqual("whole_reviewed", records[1]["review_state"])
        self.assertEqual(records[0]["candidate_id"], records[1]["candidate_id"])
        self.assertEqual([1, 2], [r["version"] for r in records])

    def test_step_traceback_invalidates_old_attempt_but_preserves_independent_explore(self):
        plan = {"version": 1, "steps": [{"step_id": "s1", "title": "derive", "objective": "prove"}]}
        model = ScriptedModelPort(
            [
                {"assessment": "NEED_PLAN", "solution_candidate": "independent conjecture"},
                {
                    "argument": "bad derivation",
                    "solution_candidate": "first full answer",
                    "answer_completeness": "complete",
                },
                {
                    "argument": "correct derivation",
                    "solution_candidate": "second full answer",
                    "answer_completeness": "complete",
                },
            ]
        )
        verifier = ScriptedVerifierPort(
            [
                {
                    "goal_gate": "NO",
                    "logic_gate": "FAIL",
                    "verdict": "TRACE_BACK",
                    "trace_back_to": 1,
                },
                {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT"},
            ]
        )
        config = {
            "max_model_calls": 5,
            "features": {"candidate_registry": True, "persistent_sessions": True},
        }
        with SolverHarness(model_port=model, verifier_port=verifier, config=config) as harness:
            harness.solve("prove", {"run_id": "rollback"})
            result = harness.solve("prove", {"run_id": "rollback", "plan": plan})
            self.assertEqual(result, harness.get_run("rollback"))
        records = result["state"]["candidate_registry"]
        latest = {record["candidate_id"]: record for record in records}
        by_text = {record["answer_text"]: record for record in latest.values()}
        self.assertEqual("draft", by_text["independent conjecture"]["review_state"])
        self.assertEqual("invalidated", by_text["first full answer"]["review_state"])
        self.assertEqual("locally_reviewed", by_text["second full answer"]["review_state"])
        self.assertEqual(1, by_text["second full answer"]["attempt_index"])

    def test_final_candidates_keep_same_text_separate_sources_and_rejected_history(self):
        plan = {"version": 1, "steps": [{"step_id": "s1", "title": "derive", "objective": "prove"}]}
        config = {
            "max_model_calls": 8,
            "max_final_solution_retries": 1,
            "features": {
                "candidate_registry": True,
                "final_generation": True,
                "final_solution_review": True,
            },
        }
        model = ScriptedModelPort(
            [
                {"argument": "valid"},
                {"final_response": "same answer"},
                {"final_response": "same answer"},
            ]
        )
        verifier = ScriptedVerifierPort(
            [
                {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT"},
                {"verdict": "REJECT", "reason": "missing argument"},
                {"verdict": "ACCEPT"},
            ]
        )
        with SolverHarness(model_port=model, verifier_port=verifier, config=config) as harness:
            result = harness.solve("prove", {"run_id": "duplicate", "plan": plan})
        records = result["state"]["candidate_registry"]
        self.assertEqual(4, len(records))
        self.assertNotEqual(records[0]["candidate_id"], records[2]["candidate_id"])
        self.assertEqual(records[0]["answer_hash"], records[2]["answer_hash"])
        self.assertEqual("eligible_unreviewed", records[1]["review_state"])
        self.assertEqual(["missing argument"], records[1]["known_objections"])
        self.assertEqual("whole_reviewed", records[3]["review_state"])
        event_ids = {event["event_id"] for event in result["events"]}
        for record in records:
            self.assertIn(record["created_event_id"], event_ids)
            self.assertTrue(set(record["source_event_refs"]).issubset(event_ids))
            self.assertTrue(set(record["evidence_refs"]).issubset(event_ids))

    def test_concrete_review_counterexample_refutes_and_replay_is_idempotent(self):
        model = ScriptedModelPort([{"assessment": "SOLVED", "solution_candidate": "wrong"}])
        with SolverHarness(
            model_port=model,
            verifier_port=ScriptedVerifierPort(
                [{"verdict": "REJECT", "counterexample": "x=0 violates the claimed positive bound"}]
            ),
            config={"features": {"candidate_registry": True}},
        ) as harness:
            result = harness.solve("prove", {"run_id": "refuted"})
            replay = harness.commit_event(
                "refuted",
                expected_revision=1,
                event={
                    "event_id": "explore-assessed-1",
                    "type": "explore_assessed",
                    "assessment": "SOLVED",
                    "round": 1,
                    "next_phase": "EXPLORE_REVIEW",
                    "summary": "Explore round 1 assessed as SOLVED; next phase EXPLORE_REVIEW",
                },
                state_updates={
                    "phase": "EXPLORE_REVIEW",
                    "exploration_findings": result["state"]["exploration_findings"],
                },
            )
            self.assertEqual(result, replay)
        self.assertEqual("refuted", result["state"]["candidate_registry"][-1]["review_state"])
        self.assertFalse(result["state"]["candidate_registry"][-1]["selection_eligible"])

    def test_disabled_registry_stays_none_without_extra_model_calls(self):
        model = ScriptedModelPort([{"assessment": "SOLVED", "solution_candidate": "answer"}])
        with SolverHarness(model_port=model) as harness:
            result = harness.solve("prove")
        self.assertIsNone(result["state"]["candidate_registry"])
        self.assertEqual(1, len(model.requests))
        self.assertFalse(any(e["type"].startswith("candidate_") for e in result["events"]))

    def test_replan_invalidates_dependent_old_candidate_and_preserves_source_history(self):
        plan = {"version": 1, "steps": [{"step_id": "s1", "title": "derive", "objective": "prove"}]}
        decision = {
            "decision": "APPROVE_REPLAN",
            "reason_summary": "failed route",
            "plan_summary": "new route",
            "forbidden_directions": ["old route"],
            "reusable_results": [],
            "trace_back_to": None,
        }
        model = ScriptedModelPort(
            [
                {
                    "argument": "bad",
                    "solution_candidate": "old answer",
                    "answer_completeness": "complete",
                },
                {**plan, "version": 2},
                {
                    "argument": "good",
                    "solution_candidate": "new answer",
                    "answer_completeness": "complete",
                },
            ]
        )
        verifier = ScriptedVerifierPort(
            [
                {"goal_gate": "NO", "logic_gate": "FAIL", "verdict": "PROPOSE_REPLAN"},
                {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT"},
            ]
        )
        with SolverHarness(
            model_port=model,
            verifier_port=verifier,
            meta_port=ScriptedModelPort([decision]),
            config={"max_model_calls": 6, "features": {"candidate_registry": True}},
        ) as harness:
            result = harness.solve("prove", {"plan": plan})
        records = result["state"]["candidate_registry"]
        old = [record for record in records if record["answer_text"] == "old answer"]
        self.assertEqual("eligible_unreviewed", old[0]["review_state"])
        self.assertEqual("invalidated", old[-1]["review_state"])
        self.assertTrue(old[-1]["invalidated_by"])
        self.assertEqual(2, records[-1]["plan_version"])
        self.assertEqual("locally_reviewed", records[-1]["review_state"])
