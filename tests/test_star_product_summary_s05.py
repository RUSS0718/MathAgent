"""S05 public summary contract for frozen ProblemSpec Runs."""

import unittest

from showcase.star_product_summary import progress_summary


class FaithfulS05SummaryTest(unittest.TestCase):
    def test_frozen_problem_spec_exposes_safe_plan_history_and_root_ledger(self):
        state = {
            "problem_spec_policy": {"enabled": True},
            "plan_version": 2,
            "attempt_index": 1,
            "plan": {"version": 2, "steps": [
                {"step_id": "current-secret-id", "objective": "private current objective"},
            ]},
            "steps": {},
            "failure_records": [{
                "kind": "replan",
                "plan_version": 1,
                "attempt_index": 0,
                "archived_plan": {"version": 1, "steps": [
                    {"step_id": "old-secret-id", "objective": "private old objective"},
                    {"step_id": "another-secret-id", "objective": "private old objective 2"},
                ]},
                "archived_steps": {"old-secret-id": {}, "another-secret-id": {}},
                "invalidated_results": [{"statement": "private proof"}],
                "rescued_results": [],
            }],
            "obligation_ledger": [
                {"obligation_id": "secret-root-id", "obligation_type": "universal",
                 "statement": "PRIVATE ROOT OBLIGATION", "status": "satisfied"},
            ],
            "verified_results_ledger": [],
        }

        summary = progress_summary(state)

        self.assertEqual({
            "covered": 1,
            "total": 1,
            "items": [{"ordinal": 1, "type": "universal", "status": "satisfied"}],
        }, summary["root_obligations"])
        self.assertEqual([
            {"plan_version": 1, "attempt_index": 0, "status": "archived",
             "step_count": 2, "outcome": "replan"},
            {"plan_version": 2, "attempt_index": 1, "status": "current",
             "step_count": 1, "outcome": None},
        ], summary["plan_history"])
        self.assertNotIn("PRIVATE", str(summary))
        self.assertNotIn("secret", str(summary))

    def test_problem_spec_disabled_preserves_the_legacy_summary_shape(self):
        state = {
            "plan_version": 1,
            "attempt_index": 0,
            "plan": {"steps": []},
            "steps": {},
            "failure_records": [],
            "verified_results_ledger": [],
        }

        self.assertEqual({
            "plan_version", "attempt_index", "steps", "failures",
            "classified_results", "meta_decision",
        }, set(progress_summary(state)))

    def test_problem_spec_freeze_is_read_from_the_saved_run_state(self):
        state = {
            "problem_spec_policy": {"enabled": False},
            "plan_version": 1,
            "attempt_index": 0,
            "plan": {"steps": []},
            "steps": {},
            "failure_records": [],
            "obligation_ledger": [{
                "obligation_id": "old-run-private-id",
                "obligation_type": "equation",
                "statement": "PRIVATE OLD SPEC",
                "status": "satisfied",
            }],
            "verified_results_ledger": [],
        }

        summary = progress_summary(state)

        self.assertNotIn("root_obligations", summary)
        self.assertNotIn("plan_history", summary)
