"""Public Solver Run recovery guards and current-spec dependency qualification."""

import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from showcase.solver_harness import ScriptedVerifierPort, SolverHarness
from showcase.star_product_recovery import resume_solver
from showcase.storage import SQLiteStore
from tests.test_faithful_auto_intake import ACCEPT, CONFIG, PROBLEM, SOLVED, SPEC, IntakePort

POLICY_VERSION = "objective-dependency-routing-v1"
ROUTED_CONFIG = {**CONFIG, "routing_policy_version": POLICY_VERSION,
                 "features": {**CONFIG["features"], "adaptive_solving": True}}


class DependencyRecoveryTest(unittest.TestCase):
    def test_spec_changed_after_exploration_is_rechecked_before_whole_review(self):
        class PlannerObserved(BaseException):
            pass

        class Port(IntakePort):
            def complete(self, request):
                if request["role"] == "planner":
                    self.requests.append(deepcopy(request))
                    raise PlannerObserved()
                return super().complete(request)

        def revise_after_finding(run, event):
            if event["type"] == "explore_assessed":
                spec = deepcopy(run["state"]["problem_spec"])
                spec["specification_version"] = 2
                spec["root_obligations"][1]["prerequisite_ids"] = [spec["root_obligations"][0]["obligation_id"]]
                harness.update_problem_spec(run["run_id"], expected_revision=run["state_revision"],
                                            problem_spec=spec)

        port = Port([SPEC, SOLVED])
        verifier = ScriptedVerifierPort([ACCEPT])
        from showcase.run_budget import RunBudgetLedger, RunBudgetLimits

        directory = self.enterContext(TemporaryDirectory())
        database = Path(directory) / "state.db"
        ledger = RunBudgetLedger(database_path=database)
        self.addCleanup(ledger.close)
        ledger.ensure("current-spec-190", RunBudgetLimits())
        harness = self.enterContext(SolverHarness(config=ROUTED_CONFIG,
            database_path=database, model_port=port, verifier_port=verifier,
            event_observer=revise_after_finding))
        with self.assertRaises(PlannerObserved):
            harness.solve(PROBLEM, {"run_id": "current-spec-190"})
        self.assertEqual([], verifier.requests)
        self.assertEqual(2, port.requests[-1]["problem_spec_version"])

    def test_recovered_rejection_on_new_independent_run_keeps_one_correction(self):
        class Crash(BaseException):
            pass

        def stop_after_review(run, event):
            if event["type"] == "solution_review_assessed":
                raise Crash()

        port = IntakePort([SPEC, SOLVED, SOLVED])
        store = SQLiteStore()
        self.addCleanup(store.close)
        verifier = ScriptedVerifierPort([
            {"verdict": "REJECT", "reason": "Include the negative root."}, ACCEPT])
        harness = self.enterContext(SolverHarness(store=store,
            config={**ROUTED_CONFIG, "max_model_calls": 10},
            model_port=port, verifier_port=verifier, event_observer=stop_after_review))
        with self.assertRaises(Crash):
            harness.solve(PROBLEM, {"run_id": "review-crash"})
        # The observer is an external interruption point; use a fresh Harness on the shared store.
        recovered_harness = self.enterContext(SolverHarness(
            store=store, config={**ROUTED_CONFIG, "max_model_calls": 10},
            model_port=port, verifier_port=verifier))
        recovered = resume_solver(recovered_harness, PROBLEM, "review-crash", None)
        self.assertEqual("completed_llm_reviewed", recovered["state"]["status"])
        self.assertEqual(2, len(verifier.requests))
        self.assertEqual(3, len(port.requests))

    def staged(self, *, dependent=True, unknown_tool=False):
        """Use public Run creation/CAS to stage an audited recovery boundary."""
        spec = deepcopy(SPEC)
        spec["root_obligations"][0]["obligation_id"] = "roots"
        spec["root_obligations"][1]["obligation_id"] = "complete"
        if dependent:
            spec["root_obligations"][1]["prerequisite_ids"] = ["roots"]
        harness = self.enterContext(SolverHarness(config=ROUTED_CONFIG))
        run = harness.solve(PROBLEM, {"run_id": "recover-190", "problem_spec": spec})
        run = harness.commit_event(run["run_id"], expected_revision=run["state_revision"],
            event={"event_id": "seed-finding", "type": "explore_assessed"}, state_updates={
                "phase": "EXPLORE_REVIEW", "status": "running",
                "adaptive_solving": {"version": "adaptive-solving-v1", "corrections": 0},
                "exploration_findings": [{"round": 1, **SOLVED}],
            })
        if unknown_tool:
            run = harness.commit_event(run["run_id"], expected_revision=run["state_revision"],
                event={"event_id": "unknown-tool:dispatch", "type": "tool_dispatched"})
        return harness, run, spec

    def test_unknown_tool_stops_before_dependency_route_or_review(self):
        harness, staged, _ = self.staged(unknown_tool=True)
        recovered = resume_solver(harness, PROBLEM, staged["run_id"], None)
        self.assertEqual(staged["state_revision"], recovered["state_revision"])
        self.assertEqual("EXPLORE_REVIEW", recovered["state"]["phase"])
        self.assertEqual([], recovered["state"].get("whole_solution_reviews", []))

    def test_recovered_solved_finding_still_enters_plan_without_minting_proof(self):
        harness, staged, _ = self.staged()
        recovered = resume_solver(harness, PROBLEM, staged["run_id"], None)
        self.assertEqual("PLAN", recovered["state"]["phase"])
        self.assertEqual(staged["state"]["config_hash"], recovered["state"]["config_hash"])
        self.assertEqual(staged["state"]["exploration_findings"], recovered["state"]["exploration_findings"])
        self.assertEqual([], recovered["state"]["verified_results_ledger"])
        self.assertEqual([], recovered["state"]["accepted_results"])

    def test_new_current_spec_dependencies_override_old_direct_candidate(self):
        harness, staged, spec = self.staged(dependent=False)
        spec["specification_version"] = 2
        spec["root_obligations"][1]["prerequisite_ids"] = ["roots"]
        revised = harness.update_problem_spec(staged["run_id"],
            expected_revision=staged["state_revision"], problem_spec=spec)
        recovered = resume_solver(harness, PROBLEM, staged["run_id"], None)
        self.assertEqual(2, recovered["state"]["specification_version"])
        self.assertEqual("PLAN", recovered["state"]["phase"])
        self.assertEqual(revised["state"]["config_hash"], recovered["state"]["config_hash"])
