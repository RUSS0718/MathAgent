"""A rejected Meta continuation cannot repeatedly re-enter the same scheduler."""

import unittest

from showcase.solver_harness import ScriptedModelPort, SolverHarness
from showcase.solver_harness.meta import run_meta
from showcase.solver_harness.progress import action_keys, guard_action
from showcase.solver_harness.routes import sync_plan_route
from tests.test_faithful_s03_job import SPEC


class AdaptiveMetaLoopTest(unittest.TestCase):
    def prepare(self, harness):
        plan = {"version": 1, "steps": [{"step_id": "s1", "title": "prove value", "objective": "prove value",
                    "method_id": "direct", "depends_on": [], "obligation_ids": ["root:value"]}]}
        run = harness.solve(SPEC["original_problem"], {"problem_spec": SPEC, "plan": plan})
        run = harness.commit_event(run["run_id"], expected_revision=run["state_revision"],
            event={"event_id": "plan", "type": "initial_plan_generated"},
            state_updates={"phase": "STEP_EXECUTE", "plan": plan,
                           "plan_version": 1, "current_step": "s1"})
        run = sync_plan_route(harness, run)
        route_id = run["state"]["active_route_id"]
        keys = action_keys(run["state"], "s1")
        progress = {"rounds": 2, "no_evidence_rounds": 2, "no_feedback_rounds": 2,
                    "blocked_actions": keys, "trigger": "local_action_blocked",
                    "route_progress": {"route_id": route_id, "no_feedback_rounds": 2,
                                       "action_failures": {key: 2 for key in keys}}}
        return harness.commit_event(run["run_id"], expected_revision=run["state_revision"],
            event={"event_id": "blocked", "type": "plan_blocked"},
            state_updates={"phase": "META_DECIDE", "progress": progress})

    def harness(self):
        return SolverHarness(config={"max_model_calls": 10, "features": {
            "serial_routes": True, "problem_spec": True, "progress_scheduling": True,
            "final_generation": True, "final_solution_review": True, "adaptive_solving": True,
            "stream_recovery": True}})

    def continue_meta(self, harness, run, decision="CONTINUE"):
        port = ScriptedModelPort([{"decision": decision, "reason_summary": "Continue proof",
            "plan_summary": "Reuse the same plan", "forbidden_directions": [],
            "reusable_results": [], "trace_back_to": None}])
        return run_meta(harness, run, meta_port=port, metadata={},
                        max_model_calls=10, max_runtime_seconds=300), port

    def test_real_meta_continue_stops_instead_of_reentering_same_blocked_route(self):
        with self.harness() as harness:
            blocked = self.prepare(harness)
            continued, port = self.continue_meta(harness, blocked)
            result = guard_action(harness, continued)
            self.assertEqual("TERMINAL", result["state"]["phase"])
            self.assertEqual("progress_action_blocked", result["state"]["result_reason"])
            self.assertEqual(blocked["state"]["progress"], result["state"]["progress"])
            self.assertEqual(1, len(port.requests))
            self.assertEqual(result, harness.get_run(result["run_id"]))

    def test_meta_receives_explicit_continue_admission_and_its_context_is_bound(self):
        with self.harness() as harness:
            run, port = self.continue_meta(harness, self.prepare(harness))
            context = port.requests[0].get("scheduler_context", {})
            self.assertIs(False, context.get("continue_allowed"))
            self.assertEqual("progress_action_blocked", context["reason"])
            self.assertEqual(context, run["state"]["meta_decision"]["scheduler_context"])

    def test_new_review_is_not_stopped_by_an_older_continue_ruling(self):
        with self.harness() as harness:
            run, _ = self.continue_meta(harness, self.prepare(harness))
            run["state"]["progress"]["rounds"] += 1
            result = guard_action(harness, run)
            self.assertEqual("META_DECIDE", result["state"]["phase"])

    def test_actual_work_after_the_ruling_is_not_the_same_meta_loop(self):
        with self.harness() as harness:
            run, _ = self.continue_meta(harness, self.prepare(harness))
            run["state"]["calls"]["later-work"] = {"role": "reasoner", "status": "completed"}
            result = guard_action(harness, run)
            self.assertEqual("META_DECIDE", result["state"]["phase"])

    def test_actual_new_feedback_can_continue_without_proof_credit(self):
        with self.harness() as harness:
            run, _ = self.continue_meta(harness, self.prepare(harness))
            ledger = run["state"]["obligation_ledger"]
            run["state"]["tool_receipts"] = [{"executed": True, "tool": "python_math",
                "input": {"code": "print(1+1)"}, "output": "2", "status": "ok"}]
            self.assertIs(run, guard_action(harness, run))
            self.assertEqual(ledger, run["state"]["obligation_ledger"])

    def test_existing_v1_run_retains_its_frozen_guard(self):
        from unittest.mock import patch

        with self.harness() as harness:
            with patch("showcase.solver_harness.progress.ADAPTIVE_SEARCH_VERSION", "adaptive-search-v1"):
                blocked = self.prepare(harness)
            run, port = self.continue_meta(harness, blocked)
            self.assertNotIn("scheduler_context", port.requests[0])
            self.assertEqual("META_DECIDE", guard_action(harness, run)["state"]["phase"])

    def test_unblocked_continue_and_explicit_replan_keep_their_authority(self):
        for decision in ("CONTINUE", "APPROVE_REPLAN"):
            with self.subTest(decision=decision), self.harness() as harness:
                run = self.prepare(harness)
                if decision == "CONTINUE":
                    run = harness.commit_event(run["run_id"], expected_revision=run["state_revision"],
                        event={"event_id": "new-target", "type": "test_seed"},
                        state_updates={"progress": {}})
                run, port = self.continue_meta(harness, run, decision)
                self.assertIs(run, guard_action(harness, run))
                self.assertEqual("STEP_EXECUTE" if decision == "CONTINUE" else "REPLAN", run["state"]["phase"])
                if decision == "CONTINUE":
                    self.assertTrue(port.requests[0]["scheduler_context"]["continue_allowed"])


if __name__ == "__main__":
    unittest.main()
