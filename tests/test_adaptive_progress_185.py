"""Actual new search feedback permits continuation without granting proof credit."""

import unittest
from unittest.mock import Mock

from showcase.solver_harness.progress import guard_action, review_progress
from tests import test_faithful_s04_progress as legacy_progress


class AdaptiveProgressTest(unittest.TestCase):
    def test_supplied_plan_initializes_adaptive_state_before_executing_it(self):
        from unittest.mock import patch

        from showcase.solver_harness import ScriptedModelPort, SolverHarness
        from showcase.solver_harness.specification import normalize_problem_spec
        from tests.test_faithful_auto_intake import CONFIG, PROBLEM, SPEC

        config = {**CONFIG, "features": {**CONFIG["features"], "adaptive_solving": True}}
        spec = normalize_problem_spec(SPEC)
        plan = {"version": 1, "steps": [{"step_id": "a", "title": "roots",
                    "objective": "Find and prove both roots", "depends_on": [],
                    "obligation_ids": [root["obligation_id"] for root in spec["root_obligations"]]}]}
        with SolverHarness(config=config, model_port=ScriptedModelPort([])) as harness:
            with patch("showcase.solver_harness.controller.run_plan", side_effect=lambda h, r, **kwargs: r):
                with patch("showcase.solver_harness.controller.advance", side_effect=lambda h, r, *args, **kwargs: r):
                    run = harness.solve(PROBLEM, {"problem_spec": spec, "plan": plan})
        self.assertEqual("adaptive-solving-v1", run["state"]["adaptive_solving"]["version"])
        self.assertEqual("supplied_plan", run["state"]["adaptive_solving"]["reason"])
        self.assertEqual("adaptive-search-v2", run["state"]["adaptive_search_policy"])

    def test_old_run_keeps_its_frozen_stagnation_policy(self):
        state = self.prepare()
        state.pop("adaptive_search_policy")
        state["progress"].pop("no_feedback_rounds")
        state["progress"].pop("search_context")
        self.feedback(state)
        patch = self.review(state)
        self.assertEqual("stagnation", patch["progress"]["trigger"])
        self.assertNotIn("no_feedback_rounds", patch["progress"])

    def initial(self, *, routes=False):
        state = legacy_progress.ProgressTest().state()
        state["adaptive_solving"] = {"version": "adaptive-solving-v1"}
        state["adaptive_search_policy"] = "adaptive-search-v2"
        if routes:
            state.update(route_policy={"enabled": True}, active_route_id="primary",
                         route_registry=[{"route_id": "primary", "status": "active", "kind": "primary"}])
        return state

    def review(self, state, **updates):
        return review_progress(state, {"type": "step_reviewed", "step_id": "a"},
                               {"phase": "CHALLENGE", **updates})

    def prepare(self, *, routes=False):
        state = self.initial(routes=routes)
        state.update(self.review(state))
        state["plan"]["steps"][0]["method_id"] = "induction"
        state.update(self.review(state))
        state["plan"]["steps"][0]["method_id"] = "contradiction"
        return state

    def feedback(self, state):
        state["tool_receipts"] = [{"tool": "python_math", "input": {"code": "print(1+1)"},
                                   "output": "2", "executed": True, "status": "ok"}]

    def test_new_tool_feedback_continues_but_does_not_satisfy_any_root(self):
        state = self.prepare()
        self.feedback(state)
        patch = self.review(state)
        self.assertNotEqual("META_DECIDE", patch.get("phase"))
        self.assertIsNone(patch["progress"]["trigger"])
        self.assertEqual(3, patch["progress"]["no_evidence_rounds"])
        self.assertEqual([], patch["progress"]["seen_roots"])
        self.assertEqual(0, patch["progress"]["no_feedback_rounds"])

    def test_duplicate_receipts_and_heartbeats_cannot_refresh_search(self):
        state = self.initial()
        self.feedback(state)
        for method in ("direct", "induction"):
            state["plan"]["steps"][0]["method_id"] = method
            state.update(self.review(state))
        state["tool_receipts"] *= 2
        state.update(heartbeat=100, updated_at="later")
        state["plan"]["steps"][0]["method_id"] = "contradiction"
        self.assertEqual("stagnation", self.review(state)["progress"]["trigger"])

    def test_new_verified_lemma_in_current_review_refreshes_search_without_root_credit(self):
        state = self.prepare()
        patch = self.review(state, verified_results_ledger=[{
            "result_id": "lemma", "category": "Lemma", "statement": "x*x >= 0",
            "valid": True, "proven": True, "evidence_level": "llm_reviewed", "dependencies": []}])
        self.assertIsNone(patch["progress"]["trigger"])
        self.assertEqual([], patch["progress"]["seen_roots"])

    def test_renamed_conjecture_cannot_refresh_search(self):
        state = self.prepare()
        patch = self.review(state, verified_results_ledger=[{
            "result_id": "new-name", "category": "Conjecture", "statement": "maybe x=1", "valid": True}])
        self.assertEqual("stagnation", patch["progress"]["trigger"])

    def test_route_local_stagnation_uses_new_feedback_without_proof_credit(self):
        state = self.prepare(routes=True)
        self.feedback(state)
        patch = self.review(state)
        self.assertIsNone(patch["progress"]["trigger"])
        self.assertEqual(3, patch["progress"]["route_progress"]["no_evidence_rounds"])
        self.assertEqual(0, patch["progress"]["route_progress"]["no_feedback_rounds"])

    def test_guard_allows_feedback_arriving_after_last_review(self):
        for routes in (False, True):
            with self.subTest(routes=routes):
                state = self.prepare(routes=routes)
                state.update(self.review(state))
                state["phase"] = "STEP_EXECUTE"
                self.feedback(state)
                run = {"run_id": "r", "state_revision": 5, "state": state}
                harness = Mock()
                self.assertIs(run, guard_action(harness, run))
                harness.commit_event.assert_not_called()

    def test_feedback_does_not_bypass_route_specification_or_budget_guards(self):
        for blocked_by in ("specification", "budget"):
            with self.subTest(blocked_by=blocked_by):
                state = self.prepare(routes=True)
                state["phase"] = "STEP_EXECUTE"
                self.feedback(state)
                active = state["route_registry"][0]
                if blocked_by == "specification":
                    active["needs_reevaluation"] = True
                else:
                    active["kind"] = "alternate"
                    state["route_budget"] = {"route_execution_allowed": False}
                harness = Mock()
                run = {"run_id": "r", "state_revision": 5, "state": state}
                self.assertIsNot(run, guard_action(harness, run))
                updates = harness.commit_event.call_args.kwargs["state_updates"]
                self.assertEqual("TERMINAL", updates["phase"])
