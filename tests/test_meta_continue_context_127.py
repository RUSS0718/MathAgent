"""Only the current CONTINUE strategy informs the resumed Reasoner."""

import unittest
from copy import deepcopy

from showcase.solver_harness.context_injection import prepare_role_context
from tests.test_meta_evidence_context_127 import evidence_run


class MetaContinueContextTest(unittest.TestCase):
    def run_with_decision(self):
        run = evidence_run()
        run["state"]["meta_decision"] = {
            "run_id": run["run_id"], "plan_version": 1, "attempt_index": 0,
            "step_id": "step2", "decided_at_revision": 8, "consumed": None,
            "decision": "CONTINUE", "plan_summary": "Use the corrected group order",
            "forbidden_directions": ["keep the wrong order"], "reusable_results": ["count"],
        }
        return run

    def test_current_strategy_reaches_both_reasoner_roles_without_mutation(self):
        for role in ("reasoner", "reason_noncoding"):
            with self.subTest(role=role):
                run = self.run_with_decision()
                before = deepcopy(run)
                context = prepare_role_context(run, {"role": role})["state"]
                self.assertEqual(run["state"]["meta_decision"], context.get("meta_decision"))
                context["meta_decision"]["plan_summary"] = "changed copy"
                self.assertEqual(before, run)

    def test_stale_decisions_and_other_roles_do_not_inherit_strategy(self):
        for changes in ({"run_id": "other"}, {"plan_version": 2}, {"attempt_index": 1},
                        {"step_id": "step1"}, {"consumed": {"event_type": "applied"}},
                        {"decision": "APPROVE_REPLAN"}):
            with self.subTest(changes=changes):
                run = self.run_with_decision()
                run["state"]["meta_decision"].update(changes)
                context = prepare_role_context(run, {"role": "reasoner"})["state"]
                self.assertNotIn("meta_decision", context)
        for role in ("step_verifier", "whole_solution_verifier", "planner", "explore"):
            with self.subTest(role=role):
                context = prepare_role_context(self.run_with_decision(), {"role": role})["state"]
                self.assertNotIn("meta_decision", context)
