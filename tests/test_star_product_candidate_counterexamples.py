"""AC-39/AC-40 public counterexamples: real contradictions and uncalibrated numbers."""

import json
import unittest

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import (POLISH, SOLVED, StarJobFixture,
                                        assert_no_uncalibrated_probability)


class StarRealContradictionReplayTest(StarJobFixture, unittest.TestCase):
    """Two same-rank candidates with genuinely different values never overstate evidence."""

    def start_best_effort(self, replies, budget):
        self.open_star(replies, SHOWCASE_STAR_BUDGET=budget)
        response = self.client.post('/api/agent/jobs', json={
            'message': '1+1', 'session_id': self.session,
            'solver_mode': 'star_limited_best_effort'}, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        return response.get_json()['job_id']

    def test_contradictory_same_rank_candidates_record_conflict_and_stable_tie_in_replay(self):
        solved = {**SOLVED, 'solution_candidate': 'x=1'}
        polish = {**POLISH, 'solution_candidate': 'x=2'}
        job_id = self.start_best_effort([solved, polish], RunBudgetLimits(
            max_model_calls=2, max_http_attempts=2, max_tool_calls=0))
        job = self.terminal(job_id)
        self.assertEqual('failed', job['status'], job)
        solver = job['result']['solver']
        self.assertEqual({'x=1', 'x=2'}, {item['answer_text']
                                          for item in solver['candidate_history']})
        decision = solver['best_effort']
        self.assertEqual('candidate_selected', decision['status'])
        self.assertIn('candidate_conflict', decision['reason_codes'])
        self.assertEqual('low', decision['confidence_level'])
        self.assertEqual(2, len(decision['reason_evidence']['candidate_conflict']))
        first = self.client.get(f'/api/agent/jobs/{job_id}/candidate-replay').get_json()
        second = self.client.get(f'/api/agent/jobs/{job_id}/candidate-replay').get_json()
        self.assertEqual(first, second)
        self.assertEqual('replay', first['evidence_kind'])
        self.assertTrue(first['audit']['matches_persisted_decision'])
        replayed = first['decision']
        self.assertEqual(decision['selected_candidate_id'], replayed['selected_candidate_id'])
        self.assertIn('candidate_conflict', replayed['reason_codes'])
        self.assertEqual(2, len(replayed['reason_evidence']['candidate_conflict']))
        self.assertEqual('low', replayed['confidence_level'])
        self.assertEqual('low', replayed['evidence_grade']['confidence_level'])
        self.assertIn('same_rank_candidate_conflict', replayed['evidence_grade']['reason_codes'])
        assert_no_uncalibrated_probability(self, first)
        self.assertEqual(2, len(self.outbound))
        evidence = self.client.get(f'/api/runs/{job_id}/evidence').get_json()
        self.assertEqual(decision, evidence['verification']['selection'])

    def test_replay_conflict_survives_service_restart_byte_stable(self):
        import os
        from unittest.mock import patch

        from showcase.flask_app import create_app

        solved = {**SOLVED, 'solution_candidate': 'x=1'}
        polish = {**POLISH, 'solution_candidate': 'x=2'}
        self.open_star([solved, polish], SHOWCASE_STAR_BUDGET=RunBudgetLimits(
            max_model_calls=2, max_http_attempts=2, max_tool_calls=0))
        response = self.client.post('/api/agent/jobs', json={
            'message': '1+1', 'session_id': self.session,
            'solver_mode': 'star_limited_best_effort'}, headers=self.headers())
        job_id = response.get_json()['job_id']
        before = self.terminal(job_id)['result']['solver']['best_effort']
        data_dir = self.data_dir
        for name in ('loopback_store', 'showcase_run_service', 'showcase_workspace_service'):
            self.app.extensions[name].close()
        with patch.dict(os.environ, {'INTERN_API_KEY': 'scripted-only'}):
            reopened = create_app({'TESTING': True, 'SHOWCASE_DATA_DIR': data_dir,
                'SHOWCASE_JOB_DELAY_SECONDS': 0, 'SHOWCASE_STAR_ENABLED': True,
                'SHOWCASE_STAR_EVIDENCE_KIND': 'fault_injection',
                'SHOWCASE_STAR_BUDGET': RunBudgetLimits(
                    max_model_calls=2, max_http_attempts=2, max_tool_calls=0)})
            try:
                client = reopened.test_client()
                # Establish the loopback login session before the replay read.
                self.assertTrue(client.get('/api/check_auth').get_json()['csrf_token'])
                replay = client.get(f'/api/agent/jobs/{job_id}/candidate-replay')
                self.assertEqual(200, replay.status_code, replay.get_json())
                payload = replay.get_json()
                self.assertTrue(payload['audit']['matches_persisted_decision'])
                self.assertEqual(before['selected_candidate_id'],
                                 payload['decision']['selected_candidate_id'])
                self.assertIn('candidate_conflict', payload['decision']['reason_codes'])
                self.assertEqual(2, len(self.outbound))
            finally:
                for name in ('loopback_store', 'showcase_run_service', 'showcase_workspace_service'):
                    reopened.extensions[name].close()



class StarUncalibratedProbabilityTest(StarJobFixture, unittest.TestCase):
    """AC-40: an uncalibrated 0.95 never becomes a displayed calibrated probability."""

    def test_step_reply_with_probability_field_is_rejected_by_strict_schema(self):
        from tests.test_star_product_planning import FEATURES, STEP
        from tests.test_star_product_tools import NEED_PLAN, PLAN, VERDICT

        confident = {**STEP, 'confidence': 0.95}
        # The reasoner owns one bounded format repair (ALIGN-10 round 2): the
        # uncalibrated reply must fail twice before the honest end.
        self.open_star([NEED_PLAN, PLAN, confident, confident],
                       SHOWCASE_STAR_FEATURES=FEATURES,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                           max_model_calls=16, max_http_attempts=16))
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual('failed', job['status'], job)
        recovery = job['result']['solver']['recovery']
        # ALIGN-04: a complete reply with an extra field is a known protocol
        # failure, not an unknown remote outcome awaiting human review.
        self.assertEqual('safe', recovery['status'])
        self.assertEqual([], recovery['unknown_calls'])
        self.assertEqual(2, len(recovery['protocol_failures']))
        self.assertEqual({'reasoner'}, {item['role'] for item in recovery['protocol_failures']})
        failure = recovery['protocol_failures'][0]
        self.assertEqual('invalid_role_schema', failure['error_category'])
        self.assertEqual('stop', failure['finish_reason'])
        self.assertEqual(1, sum(item['repair_attempts'] for item in recovery['protocol_failures']))
        self.assertEqual('partial_aborted', job['result']['solver']['status'])
        self.assertEqual(4, len(self.outbound))
        public = json.dumps([job, self.report(job_id),
                             self.client.get(f'/api/runs/{job_id}/evidence').get_json(),
                             self.client.get(f'/api/agent/jobs/{job_id}/candidate-replay')
                             .get_json()])
        # A raw-text '0.95' scan misfires on wall-clock fields; scan parsed output.
        assert_no_uncalibrated_probability(self, public)
        self.assertNotIn('calibrated', public)
        self.assertEqual([], job['result']['solver']['candidate_history'])

    def test_verifier_reply_with_probability_field_is_rejected_not_normalized(self):
        from tests.test_star_product_planning import FEATURES, STEP
        from tests.test_star_product_tools import NEED_PLAN, PLAN

        confident = {'goal_gate': 'YES', 'logic_gate': 'PASS', 'verdict': 'ACCEPT',
                     'objection': '', 'confidence': 0.95}
        # The verifier's bounded format repair gets the same uncalibrated body.
        self.open_star([NEED_PLAN, PLAN, STEP, confident, confident],
                       SHOWCASE_STAR_FEATURES=FEATURES,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                           max_model_calls=16, max_http_attempts=16))
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual('failed', job['status'], job)
        stream = self.client.get(f'/api/agent/jobs/{job_id}/events').get_data(as_text=True)
        reviewed = [json.loads(line[6:]) for line in stream.splitlines()
                    if line.startswith('data: ')
                    and json.loads(line[6:]).get('solver_event_type') == 'step_reviewed']
        self.assertTrue(reviewed)
        self.assertNotIn('ACCEPT', [event.get('verdict') for event in reviewed])
        evidence = self.client.get(f'/api/runs/{job_id}/evidence').get_json()
        public = stream + json.dumps([job, self.report(job_id), evidence])
        # A raw-text '0.95' scan misfires on wall-clock fields; scan parsed output.
        assert_no_uncalibrated_probability(self, stream, job, self.report(job_id), evidence)
        self.assertNotIn('"confidence"', public)
