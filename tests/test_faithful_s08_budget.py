"""Serial route expansion retains shared closeout and unknown reservations."""
import unittest

from showcase.run_budget import RunBudgetLedger, RunBudgetLimits
from showcase.solver_harness.progress import review_progress
from showcase.solver_harness.route_budget import derive_route_budget


class RouteBudgetTest(unittest.TestCase):
    def test_expansion_stops_for_tokens_deadline_and_shared_unknown_charge(self):
        with RunBudgetLedger() as ledger:
            ledger.ensure('r', RunBudgetLimits(max_model_calls=10, max_http_attempts=10, max_tokens=1000))
            base = {'preflight_valid': True, 'effective_deadline_at': 100,
                    'closing_reserve': {'model_calls': 2, 'http_attempts': 2, 'tokens': 500, 'time_seconds': 20},
                    'planner_reserve': {'model_calls': 1, 'http_attempts': 1, 'tokens': 200, 'time_seconds': 10},
                    'work_unit_reserve': {'model_calls': 2, 'http_attempts': 2, 'tokens': 200, 'time_seconds': 20}}
            self.assertTrue(derive_route_budget(ledger.connection, 'r', base, now=0)['expansion_allowed'])
            self.assertFalse(derive_route_budget(ledger.connection, 'r', base, now=51)['expansion_allowed'])
            base['closing_reserve']['tokens'] = 700
            self.assertFalse(derive_route_budget(ledger.connection, 'r', base, now=0)['expansion_allowed'])

    def test_alternate_progress_resets_then_counts_three_new_stagnant_rounds(self):
        state = {'progress_policy': {'enabled': True, 'version': 'progress-v1'},
                 'route_policy': {'enabled': True}, 'active_route_id': 'alternate',
                 'problem_spec': {}, 'progress': {'no_evidence_rounds': 3},
                 'plan': {'steps': [{'step_id': 's', 'obligation_ids': ['root:a'], 'method_id': 'direct'}]}}
        event = {'type': 'step_reviewed', 'step_id': 's', 'valid': True}
        state.update(review_progress(state, event, {'obligation_ledger': [{'obligation_id': 'root:a', 'status': 'satisfied'}]}))
        for _ in range(3):
            state.update(review_progress(state, event, {'obligation_ledger': [{'obligation_id': 'root:a', 'status': 'satisfied'}]}))
        self.assertEqual(3, state['progress']['route_progress']['no_evidence_rounds'])
