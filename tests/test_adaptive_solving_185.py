"""Minimal regressions for optional direct review and one mathematical correction."""

import unittest
from unittest.mock import patch

from showcase.solver_harness import ScriptedVerifierPort, SolverHarness
from tests.test_faithful_auto_intake import ACCEPT, CONFIG, PROBLEM, SOLVED, SPEC, IntakePort


class AdaptiveSolvingTest(unittest.TestCase):
    def test_search_state_ignores_heartbeats_but_binds_scope_and_actual_feedback(self):
        from copy import deepcopy

        from showcase.solver_harness.adaptive_solving import search_context

        state = {"problem_spec": deepcopy(SPEC)}
        original = search_context(state)
        state.update(updated_at="later", counters={"model_calls": 100}, heartbeat=100)
        self.assertEqual(original, search_context(state))
        state["tool_receipts"] = [{"tool": "python_math", "executed": True, "output": "x=-1"}]
        feedback = search_context(state)
        self.assertNotEqual(original, feedback)
        state["tool_receipts"] *= 2
        self.assertEqual(feedback, search_context(state))
        state["tool_receipts"][1] = {**state["tool_receipts"][1], "input": {"code": "different probe"}}
        self.assertNotEqual(feedback, search_context(state))
        state["problem_spec"]["domain"] = "positive real numbers"
        self.assertNotEqual(feedback, search_context(state))

    def test_renamed_conjectures_and_duplicate_proofs_do_not_refresh_search_state(self):
        from showcase.solver_harness.adaptive_solving import search_context

        state = {"problem_spec": SPEC, "verified_results_ledger": []}
        original = search_context(state)
        state["verified_results_ledger"] = [{"category": "Conjecture", "statement": "x=1",
                                             "result_id": "fresh-call:conjecture", "valid": True}]
        self.assertEqual(original, search_context(state))
        lemma = {"category": "Lemma", "statement": "x*x >= 0", "valid": True,
                 "proven": True, "evidence_level": "llm_reviewed", "dependencies": [],
                 "result_id": "original-lemma"}
        state["verified_results_ledger"].append(lemma)
        proved = search_context(state)
        self.assertNotEqual(original, proved)
        state["verified_results_ledger"].append({**lemma, "result_id": "new-name"})
        self.assertEqual(proved, search_context(state))

    def test_ordinary_solve_accepts_omitted_optional_metadata(self):
        port = IntakePort([SPEC, SOLVED])
        config = {**CONFIG, "features": {**CONFIG["features"], "adaptive_solving": True}}
        with SolverHarness(config=config, model_port=port,
                           verifier_port=ScriptedVerifierPort([ACCEPT])) as harness:
            run = harness.solve(PROBLEM)
        self.assertEqual("completed_llm_reviewed", run["state"]["status"])

    def solve(self, reviews, candidates, *, calls=10):
        config = {**CONFIG, "max_model_calls": calls,
                  "features": {**CONFIG["features"], "adaptive_solving": True}}
        port = IntakePort([SPEC, *candidates])
        verifier = ScriptedVerifierPort(reviews)
        harness = self.enterContext(SolverHarness(config=config, model_port=port,
                                                  verifier_port=verifier))
        run = harness.solve(PROBLEM, {})
        return harness, run, port, verifier

    def test_complete_candidate_skips_polish_but_keeps_independent_bound_review(self):
        _, run, port, verifier = self.solve([ACCEPT], [SOLVED])
        self.assertEqual("completed_llm_reviewed", run["state"]["status"])
        self.assertEqual(["problem_intake", "explore"], [r["role"] for r in port.requests])
        self.assertEqual(1, len(verifier.requests))
        self.assertEqual(SOLVED["solution_candidate"], verifier.requests[0]["solution_candidate"])
        self.assertEqual("adaptive-solving-v1", run["state"]["adaptive_solving"]["version"])
        self.assertEqual("explore_direct", run["state"]["whole_solution_reviews"][0]["source"]["origin"])

    def test_concrete_objection_gets_one_correction_and_new_review_identity(self):
        rejected = {"verdict": "REJECT", "reason": "The negative root is omitted."}
        draft = {**SOLVED, "solution_candidate": "x=1"}
        _, run, port, verifier = self.solve([rejected, ACCEPT], [draft, SOLVED])
        self.assertEqual("completed_llm_reviewed", run["state"]["status"])
        self.assertEqual(2, len(verifier.requests))
        self.assertNotEqual(verifier.requests[0]["call_id"], verifier.requests[1]["call_id"])
        self.assertEqual(rejected["reason"], port.requests[-1]["review_feedback"]["reason"])
        self.assertEqual(2, len(run["state"]["whole_solution_reviews"]))

    def test_second_rejection_routes_to_planning_without_third_attempt(self):
        rejected = {"verdict": "REJECT", "reason": "Completeness is missing."}
        with patch("showcase.solver_harness.controller.generate_initial_plan",
                   side_effect=lambda harness, run, **kwargs: run):
            _, run, port, verifier = self.solve([rejected, rejected], [SOLVED, SOLVED])
        self.assertEqual("PLAN", run["state"]["phase"])
        self.assertEqual("whole_review_requires_planning", run["state"]["adaptive_solving"]["reason"])
        self.assertEqual(3, len(port.requests))
        self.assertEqual(2, len(verifier.requests))

    def test_unspecific_rejection_goes_to_planning_without_guessing_error(self):
        with patch("showcase.solver_harness.controller.generate_initial_plan",
                   side_effect=lambda harness, run, **kwargs: run):
            _, run, port, verifier = self.solve([{"verdict": "REJECT"}], [SOLVED])
        self.assertEqual("PLAN", run["state"]["phase"])
        self.assertEqual(2, len(port.requests))
        self.assertEqual(1, len(verifier.requests))

    def test_exhaustion_does_not_create_a_correction_or_reset_budget(self):
        _, run, port, verifier = self.solve([], [SOLVED], calls=2)
        self.assertEqual("partial_budget_exhausted", run["state"]["status"])
        self.assertEqual(2, len(port.requests))
        self.assertEqual([], verifier.requests)
        self.assertEqual(0, run["state"]["adaptive_solving"]["corrections"])

    def test_recovered_completed_review_still_performs_correction_without_replay(self):
        self.recover_at("solution_review_assessed")

    def test_recovered_committed_rejection_still_performs_correction_once(self):
        self.recover_at("adaptive_candidate_correction")

    def recover_at(self, event_type):
        """Interrupt either side of the review-to-routing commit boundary."""
        from showcase.star_product_recovery import resume_solver

        class Crash(BaseException):
            pass

        config = {**CONFIG, "max_model_calls": 10, "max_total_duration_seconds": 3600,
                  "features": {**CONFIG["features"], "adaptive_solving": True}}
        port = IntakePort([SPEC, SOLVED, SOLVED])
        verifier = ScriptedVerifierPort([
            {"verdict": "REJECT", "reason": "Check the negative root."}, ACCEPT])
        harness = self.enterContext(SolverHarness(config=config, model_port=port,
                                                  verifier_port=verifier))
        original = harness.commit_event

        def crash_before_review_commit(*args, **kwargs):
            if kwargs["event"]["type"] == event_type:
                raise Crash()
            return original(*args, **kwargs)

        with patch.object(harness, "commit_event", side_effect=crash_before_review_commit):
            with self.assertRaises(Crash):
                harness.solve(PROBLEM, {"run_id": "adaptive-crash"})
        harness._product_recovery = True
        run = resume_solver(harness, PROBLEM, "adaptive-crash", None)
        self.assertEqual("completed_llm_reviewed", run["state"]["status"])
        self.assertEqual(2, len(verifier.requests))
        self.assertEqual(3, len(port.requests))
