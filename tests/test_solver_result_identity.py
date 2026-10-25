"""Supplementary historical-record counterexamples; Job acceptance lives separately."""

import unittest

from showcase.solver_harness.finalize import valid_facts
from showcase.solver_harness.replan import _reusable
from showcase.solver_harness.results import stable_unique_results


class ResultIdentityTest(unittest.TestCase):
    def test_first_string_identity_wins_without_merging_or_collapsing_missing_ids(self):
        records = [
            {"result_id": "same", "statement": "first", "invalidated": True},
            {"result_id": "same", "statement": "later valid"},
            {"statement": "legacy"}, {"statement": "legacy"},
            {"result_id": "", "statement": "empty first"},
            {"result_id": "", "statement": "empty later"},
            {"result_id": 1}, {"result_id": 1},
        ]
        unique = stable_unique_results(records)
        self.assertEqual([records[i] for i in [0, 2, 3, 4, 6, 7]], unique)
        self.assertIs(records[0], unique[0])
        self.assertEqual(8, len(records))

    def test_final_deduplicates_before_validity_but_rescue_after_eligibility(self):
        first = {"result_id": "same", "statement": "invalid first", "source": "old",
                 "dependencies": [], "evidence_level": "llm_reviewed", "invalidated": True}
        later = {**first, "statement": "valid later", "invalidated": False}
        state = {"accepted_results": [first], "verified_results_ledger": [later],
                 "plan": {"steps": [{"step_id": "old"}]}, "steps": {}}
        self.assertEqual([], valid_facts(state))
        rescued, excluded = _reusable(state, {"reusable_results": ["same"]})
        self.assertEqual([later], rescued)
        self.assertEqual([first], excluded)
        self.assertTrue(state["accepted_results"][0]["invalidated"])

    def test_invalid_dependency_conjecture_and_unsupported_history_stay_excluded(self):
        base = {"source": "old", "dependencies": [], "evidence_level": "llm_reviewed"}
        records = [
            {**base, "result_id": "dead", "statement": "archived"},
            {**base, "result_id": "dependent", "statement": "dependent", "dependencies": ["dead"]},
            {**base, "result_id": "guess", "statement": "guess", "category": "Conjecture",
             "evidence_level": "conjecture"},
            {**base, "result_id": "unsupported", "statement": "unsupported", "evidence_level": "none"},
            {**base, "result_id": "unselected", "statement": "unselected"},
        ]
        state = {"accepted_results": records, "verified_results_ledger": [],
                 "plan": {"steps": [{"step_id": "old"}]}, "steps": {},
                 "failure_records": [{"invalidated_results": [records[0]]}]}
        self.assertEqual([records[-1]], valid_facts(state))
        rescued, _ = _reusable(state, {"reusable_results": ["dependent", "guess", "unsupported"]})
        self.assertEqual([], rescued)
