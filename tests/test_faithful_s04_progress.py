"""S04 counterexamples for structural method identity and persistent progress."""

import unittest

from showcase.solver_harness.progress import normalize_method, review_progress


class ProgressTest(unittest.TestCase):
    def state(self):
        return {
            "progress_policy": {"enabled": True, "version": "progress-v1"},
            "specification_version": 1,
            "current_step": "a",
            "plan": {"steps": [{"step_id": "a", "obligation_ids": ["root"], "method_id": "direct"}]},
            "obligation_ledger": [{"obligation_id": "root", "status": "open"}],
        }

    def review(self, state, **updates):
        return review_progress(state, {"type": "step_reviewed", "step_id": "a"},
                               {"phase": "CHALLENGE", **updates})

    def test_unknown_names_share_one_bucket(self):
        self.assertEqual("unknown", normalize_method("a novel renamed method"))
        self.assertEqual("unknown", normalize_method("Direct"))
        self.assertEqual("induction", normalize_method("induction"))

    def test_second_same_method_failure_blocks(self):
        state = self.state()
        state.update(self.review(state))
        patch = self.review(state)
        self.assertEqual("META_DECIDE", patch["phase"])
        self.assertEqual("local_action_blocked", patch["progress"]["trigger"])

    def test_different_methods_still_stagnate_after_three_rounds(self):
        state = self.state()
        for method in ("direct", "induction", "contradiction"):
            state["plan"]["steps"][0]["method_id"] = method
            state.update(self.review(state))
        self.assertEqual(3, state["progress"]["no_evidence_rounds"])
        self.assertEqual("stagnation", state["progress"]["trigger"])

    def test_new_root_evidence_resets_but_duplicate_does_not(self):
        state = self.state()
        state.update(self.review(state))
        patch = self.review(state, obligation_ledger=[{"obligation_id": "root", "status": "satisfied"}])
        self.assertEqual(0, patch["progress"]["no_evidence_rounds"])
        state.update(patch)
        state["obligation_ledger"] = [{"obligation_id": "root", "status": "satisfied"}]
        self.assertEqual(1, self.review(state)["progress"]["no_evidence_rounds"])

    def test_legacy_and_reads_do_not_count(self):
        self.assertEqual({}, review_progress({}, {"type": "step_reviewed"}, {}))
        self.assertEqual({}, review_progress(self.state(), {"type": "call_audit"}, {}))

    def test_distinct_auxiliary_targets_do_not_share_action_identity(self):
        from showcase.solver_harness.progress import action_keys
        state = self.state()
        step = state["plan"]["steps"][0]
        step.update(obligation_ids=[], auxiliary_goal_ids=["factor"])
        first = action_keys(state, "a")
        step["auxiliary_goal_ids"] = ["bound"]
        self.assertNotEqual(first, action_keys(state, "a"))

    def test_protocol_failure_is_not_a_mathematical_round(self):
        self.assertEqual({}, review_progress(self.state(),
                         {"type": "step_reviewed", "valid": False}, {}))

    def test_renaming_and_replanning_do_not_reset(self):
        state = self.state()
        state.update(self.review(state))
        state["plan"]["steps"][0].update(step_id="renamed", objective="different prose")
        patch = review_progress(state, {"type": "step_reviewed", "step_id": "renamed"}, {"phase": "CHALLENGE"})
        self.assertEqual("local_action_blocked", patch["progress"]["trigger"])


class ProgressHarnessTest(unittest.TestCase):
    def test_real_challenge_reviews_count_once_and_reads_do_not_dispatch(self):
        from test_faithful_s03_harness import SPEC_CONFIG, problem_spec

        from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort, SolverHarness
        problem = "Prove both directions."
        model = ScriptedModelPort([
            {"argument": "first attempt", "claims": [{"statement": "candidate"}]},
            {"argument": "reworded attempt", "claims": [{"statement": "candidate again"}]},
        ])
        verifier = ScriptedVerifierPort([
            {"goal_gate": "PARTIAL", "logic_gate": "UNCERTAIN", "verdict": "CHALLENGE", "objection": "missing proof"},
            {"goal_gate": "PARTIAL", "logic_gate": "UNCERTAIN", "verdict": "CHALLENGE", "objection": "still missing proof"},
        ])
        plan = {"version": 1, "steps": [{
            "step_id": "a", "title": "proof", "objective": "prove directions",
            "obligation_ids": ["root:necessary", "root:sufficient"], "method_id": "direct",
        }]}
        with SolverHarness(config={**SPEC_CONFIG, "max_model_calls": 10,
                "features": {**SPEC_CONFIG["features"], "progress_scheduling": True}},
                model_port=model, verifier_port=verifier) as harness:
            run = harness.solve(problem, {"run_id": "progress", "problem_spec": problem_spec(problem), "plan": plan})
            self.assertEqual("META_DECIDE", run["state"]["phase"])
            self.assertEqual(2, run["state"]["progress"]["rounds"])
            self.assertEqual("local_action_blocked", run["state"]["progress"]["trigger"])
            before = run["state"]["counters"]
            self.assertEqual(run, harness.get_run("progress"))
            self.assertEqual(before, harness.get_run("progress")["state"]["counters"])
            reviews = [event for event in run["events"] if event["type"] == "step_reviewed"]
            self.assertEqual(2, len(reviews))
            self.assertEqual(2, reviews[-1]["progress"]["rounds"])

    def test_work_unit_normalizes_unregistered_methods(self):
        from showcase.solver_harness.specification import normalize_work_units
        units = normalize_work_units([{"work_unit_id": "a", "obligation_ids": ["root"],
                                      "method_id": "renamed direct proof"}], [{"obligation_id": "root"}])
        self.assertEqual("unknown", units[0]["method_id"])


class IntermediateProgressTest(unittest.TestCase):
    def test_only_frozen_prerequisites_count_and_cannot_be_reworded_for_credit(self):
        state = ProgressTest().state()
        state["problem_spec"] = {
            "root_obligations": [{"obligation_id": "root", "prerequisite_ids": ["factor"]}],
            "auxiliary_goals": [{"goal_id": "factor"}, {"goal_id": "unrelated"}],
        }
        step = state["plan"]["steps"][0]
        step["auxiliary_goal_ids"] = ["unrelated"]
        updates = {"phase": "STEP_EXECUTE", "steps": {"a": {
            "verification": {"valid": True, "verdict": "ACCEPT"}}}}
        event = {"type": "step_reviewed", "step_id": "a"}
        first = review_progress(state, event, updates)
        self.assertEqual(1, first["progress"]["no_evidence_rounds"])
        state.update(first)
        step["auxiliary_goal_ids"] = ["factor"]
        second = review_progress(state, event, updates)
        self.assertEqual(0, second["progress"]["no_evidence_rounds"])
        state.update(second)
        step["objective"] = "reworded factor proof"
        third = review_progress(state, event, updates)
        self.assertEqual(1, third["progress"]["no_evidence_rounds"])


class ProgressTransactionTest(unittest.TestCase):
    def test_review_replay_cas_and_reopen_preserve_counts(self):
        import tempfile
        from pathlib import Path

        from test_faithful_s03_harness import SPEC_CONFIG, problem_spec

        from showcase.solver_harness import SolverHarness, SolverRevisionConflictError
        config = {**SPEC_CONFIG, "features": {**SPEC_CONFIG["features"], "progress_scheduling": True}}
        problem = "Prove both directions."
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite"
            with SolverHarness(database_path=path, config=config) as harness:
                initial = harness.solve(problem, {"run_id": "cas", "problem_spec": problem_spec(problem)})
                event = {"event_id": "review-1", "type": "step_reviewed", "step_id": "a"}
                patch = {"phase": "CHALLENGE", "current_step": "a"}
                first = harness.commit_event("cas", expected_revision=initial["state_revision"], event=event, state_updates=patch)
                replay = harness.commit_event("cas", expected_revision=initial["state_revision"], event=event, state_updates=patch)
                self.assertEqual(first, replay)
                with self.assertRaises(SolverRevisionConflictError):
                    harness.commit_event("cas", expected_revision=initial["state_revision"],
                                         event={**event, "event_id": "stale"}, state_updates=patch)
                self.assertEqual(first, harness.get_run("cas"))
            with SolverHarness(database_path=path, config=config) as reopened:
                self.assertEqual(first, reopened.get_run("cas"))
                self.assertEqual(1, reopened.get_run("cas")["state"]["progress"]["rounds"])

    def test_guard_allows_different_method_and_preserves_budget_on_stop(self):
        from showcase.solver_harness.progress import guard_action
        state = ProgressTest().state()
        state.update(phase="STEP_EXECUTE", progress={"blocked_actions": ["root:direct"]},
                     budget={"deadline": "original", "unknown": 7})
        run = {"state": state}
        state["plan"]["steps"][0]["method_id"] = "induction"
        self.assertIs(run, guard_action(None, run))
        state["phase"] = "META_DECIDE"
        state["plan"]["steps"][0]["method_id"] = "direct"
        self.assertIs(run, guard_action(None, run))


class EvidenceEpochTest(unittest.TestCase):
    def test_related_prerequisite_unlocks_root_but_unrelated_root_stays_blocked(self):
        state = ProgressTest().state()
        state["progress"] = {"blocked_actions": ["root:direct", "other:direct"],
                             "action_failures": {"root:direct": 2, "other:direct": 2}}
        state["problem_spec"] = {
            "root_obligations": [{"obligation_id": "root", "prerequisite_ids": ["factor"]},
                                 {"obligation_id": "other"}],
            "auxiliary_goals": [{"goal_id": "factor"}],
        }
        state["plan"]["steps"][0].update(obligation_ids=[], auxiliary_goal_ids=["factor"])
        patch = review_progress(state, {"type": "step_reviewed", "step_id": "a"}, {
            "phase": "STEP_EXECUTE", "steps": {"a": {"verification": {"valid": True, "verdict": "ACCEPT"}}}})
        self.assertNotIn("root:direct", patch["progress"]["blocked_actions"])
        self.assertIn("other:direct", patch["progress"]["blocked_actions"])


class ProgressIntegrationBoundaryTest(unittest.TestCase):
    def test_blocked_stop_keeps_budget_and_unknown_call(self):
        from test_faithful_s03_harness import SPEC_CONFIG, problem_spec

        from showcase.solver_harness import SolverHarness
        from showcase.solver_harness.progress import guard_action
        config = {**SPEC_CONFIG, "features": {**SPEC_CONFIG["features"], "progress_scheduling": True}}
        with SolverHarness(config=config) as harness:
            run = harness.solve("prove", {"run_id": "stop", "problem_spec": problem_spec("prove")})
            run = harness.commit_event("stop", expected_revision=run["state_revision"],
                event={"event_id": "fixture", "type": "fixture_loaded"}, state_updates={
                    "phase": "STEP_EXECUTE", "current_step": "a", "plan": {"steps": [{
                        "step_id": "a", "obligation_ids": ["root:necessary"], "method_id": "direct"}]},
                    "progress": {"blocked_actions": ["root:necessary:direct"]},
                    "budget": {"deadline": "original", "unknown_reserve": 7},
                    "calls": {"unresolved": {"status": "unknown"}},
                })
            stopped = guard_action(harness, run)
            self.assertEqual("TERMINAL", stopped["state"]["phase"])
            for key in ("budget", "calls", "counters"):
                self.assertEqual(run["state"][key], stopped["state"][key])

    def test_replan_replaces_old_work_unit_mapping_with_new_method(self):
        from test_faithful_s03_harness import SPEC_CONFIG, problem_spec
        from test_solver_harness_replan import DECISION

        from showcase.solver_harness import ScriptedModelPort, SolverHarness
        from showcase.storage import SQLiteStore
        config = {**SPEC_CONFIG, "max_model_calls": 4,
                  "features": {**SPEC_CONFIG["features"], "progress_scheduling": True}}
        old = {"version": 1, "steps": [{"step_id": "old", "title": "proof", "objective": "prove",
               "obligation_ids": ["root:necessary", "root:sufficient"], "method_id": "direct"}]}
        new = {"version": 2, "steps": [{**old["steps"][0], "step_id": "new", "method_id": "induction"}]}
        with SQLiteStore(":memory:") as store:
            with SolverHarness(store=store, config=config) as harness:
                run = harness.solve("prove", {"run_id": "replan", "problem_spec": problem_spec("prove"), "plan": old})
                harness.commit_event("replan", expected_revision=run["state_revision"],
                    event={"event_id": "fixture", "type": "fixture_loaded"}, state_updates={
                        "phase": "META_DECIDE", "plan": old, "plan_version": 1,
                        "current_step": "old", "progress": {"blocked_actions": ["root:necessary:direct"]}})
            with SolverHarness(store=store, config=config,
                    meta_port=ScriptedModelPort([DECISION]), model_port=ScriptedModelPort([
                        new, {"argument": "induction proof", "claims": []}])) as harness:
                result = harness.solve("prove", {"run_id": "replan"})
                self.assertEqual("new", result["state"]["work_units"][0]["work_unit_id"])
                self.assertEqual("induction", result["state"]["work_units"][0]["method_id"])
                self.assertEqual("induction", result["state"]["plan"]["steps"][0]["method_id"])


class LegacyProgressBoundaryTest(unittest.TestCase):
    def test_disabled_run_and_planner_schema_preserve_old_shape(self):
        from showcase.solver_harness import SolverHarness
        from showcase.solver_harness.intern_schemas import response_schema
        with SolverHarness() as harness:
            run = harness.solve("prove", {"run_id": "legacy"})
            self.assertNotIn("progress_policy", run["state"])
            self.assertNotIn("progress", run["state"])
            self.assertEqual(run, harness.solve("prove", {"run_id": "legacy"}))
        request = {"role": "planner", "problem_spec": {}}
        old = response_schema(request)["properties"]["steps"]["items"]["properties"]
        self.assertNotIn("method_id", old)
        new = response_schema({**request, "progress_policy": {"enabled": True}})
        self.assertIn("method_id", new["properties"]["steps"]["items"]["properties"])


class CompletedRootProgressTest(unittest.TestCase):
    def test_prerequisite_of_completed_root_cannot_refresh_stagnation(self):
        state = ProgressTest().state()
        state["obligation_ledger"] = [{"obligation_id": "root", "status": "satisfied"},
                                      {"obligation_id": "open", "status": "open"}]
        state["progress"] = {"seen_roots": ["root"], "no_evidence_rounds": 2}
        state["problem_spec"] = {
            "root_obligations": [{"obligation_id": "root", "prerequisite_ids": ["factor"]},
                                 {"obligation_id": "open"}],
            "auxiliary_goals": [{"goal_id": "factor"}],
        }
        state["plan"]["steps"][0].update(obligation_ids=[], auxiliary_goal_ids=["factor"])
        patch = review_progress(state, {"type": "step_reviewed", "step_id": "a"}, {
            "phase": "STEP_EXECUTE", "steps": {"a": {"verification": {"valid": True, "verdict": "ACCEPT"}}}})
        self.assertEqual(3, patch["progress"]["no_evidence_rounds"])
        self.assertEqual("stagnation", patch["progress"]["trigger"])
