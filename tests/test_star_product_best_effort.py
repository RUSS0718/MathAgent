"""Candidate selection through authenticated STAR Job, S4 and read-only replay."""
import unittest

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import SOLVED, StarJobFixture


class StarBestEffortTest(StarJobFixture, unittest.TestCase):
    def test_explicit_limited_best_effort_selects_without_extra_call(self):
        self.open_star([SOLVED], SHOWCASE_STAR_BUDGET=RunBudgetLimits(
            max_model_calls=1, max_http_attempts=1, max_tool_calls=0))
        response = self.client.post('/api/agent/jobs', json={
            'message': '1+1', 'session_id': self.session,
            'solver_mode': 'star_limited_best_effort'}, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        job_id = response.get_json()['job_id']
        job = self.terminal(job_id)
        self.assertEqual('failed', job['status'])
        result = job['result']
        self.assertEqual('star_limited_best_effort', result['solver_mode'])
        self.assertEqual('2', result['final_response'])
        solver = result['solver']
        self.assertEqual('candidate_selected', solver['best_effort']['status'])
        self.assertEqual('2', solver['candidate_history'][0]['answer_text'])
        self.assertEqual(1, len(self.outbound))
        check = self.report(job_id)['checks']
        self.assertEqual(solver['best_effort'], check['selection'])
        self.assertEqual('same_artifact', check['binding'])
        self.assertEqual('needs_review', check['acceptance'])
        first = self.client.get(f'/api/agent/jobs/{job_id}/candidate-replay')
        self.assertEqual(200, first.status_code, first.get_json())
        self.assertEqual('replay', first.get_json()['evidence_kind'])
        self.assertTrue(first.get_json()['audit']['matches_persisted_decision'])
        self.assertEqual(first.get_json(), self.client.get(
            f'/api/agent/jobs/{job_id}/candidate-replay').get_json())
        self.assertEqual(solver, self.job(job_id)['result']['solver'])
        self.assertEqual(1, len(self.outbound))

    def test_challenge_review_only_updates_the_actual_complete_candidate(self):
        from tests.star_product_support import ACCEPT
        from tests.test_star_product_challenge import CHALLENGE
        from tests.test_star_product_planning import FEATURES, STEP
        from tests.test_star_product_tools import NEED_PLAN, PLAN, VERDICT

        self.open_star([NEED_PLAN, PLAN,
            {**STEP, 'solution_candidate': 'old complete answer', 'answer_completeness': 'complete'},
            CHALLENGE,
            {**STEP, 'solution_candidate': 'new complete answer', 'answer_completeness': 'complete'},
            VERDICT, {'final_response': '2'}, ACCEPT],
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=10, max_http_attempts=10))
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual('succeeded', job['status'], job)
        history = self.job(job_id)['result']['solver']['candidate_history']
        old = [v for v in history if v['answer_text'] == 'old complete answer']
        new = [v for v in history if v['answer_text'] == 'new complete answer']
        self.assertTrue(new, history)
        self.assertEqual('eligible_unreviewed', old[-1]['review_state'])
        self.assertEqual('locally_reviewed', new[-1]['review_state'])
        self.assertEqual([1, 2], [v['version'] for v in old])
        self.assertEqual([1, 2], [v['version'] for v in new])
        final = [v for v in history if v['source_phase'] == 'FINAL_GENERATE']
        self.assertEqual(['eligible_unreviewed', 'whole_reviewed'], [v['review_state'] for v in final])

    def start_best_effort(self):
        response = self.client.post('/api/agent/jobs', json={
            'message': '1+1', 'session_id': self.session,
            'solver_mode': 'star_limited_best_effort'}, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        job_id = response.get_json()['job_id']
        return job_id, self.terminal(job_id)

    def test_conflict_retains_both_complete_candidates_and_qualitative_grade(self):
        from tests.star_product_support import POLISH

        self.open_star([SOLVED, POLISH], SHOWCASE_STAR_BUDGET=RunBudgetLimits(
            max_model_calls=2, max_http_attempts=2, max_tool_calls=0))
        job_id, job = self.start_best_effort()
        self.assertEqual('1+1=2', job['result']['final_response'])
        solver = job['result']['solver']
        self.assertEqual(['2', '1+1=2'], [v['answer_text'] for v in solver['candidate_history']])
        decision = solver['best_effort']
        self.assertIn('candidate_conflict', decision['reason_codes'])
        self.assertEqual('low', decision['confidence_level'])
        self.assertEqual(2, len(decision['reason_evidence']['candidate_conflict']))
        self.assertEqual(2, len(self.outbound))
        stream = self.client.get(f'/api/agent/jobs/{job_id}/events').get_data(as_text=True)
        self.assertIn('best_effort_selected', stream)
        evidence = self.client.get(f'/api/runs/{job_id}/evidence').get_json()
        self.assertEqual('star_limited_best_effort', evidence['mode'])
        self.assertEqual(decision, evidence['verification']['selection'])

    def test_empty_candidates_are_honest_and_full_modes_remain_gated(self):
        from tests.test_star_product_tools import NEED_PLAN

        self.open_star([NEED_PLAN], SHOWCASE_STAR_BUDGET=RunBudgetLimits(
            max_model_calls=1, max_http_attempts=1, max_tool_calls=0))
        job_id, job = self.start_best_effort()
        self.assertEqual('failed', job['status'])
        self.assertTrue(job['result']['final_response'].strip())
        self.assertNotEqual('2', job['result']['final_response'])
        solver = job['result']['solver']
        self.assertEqual([], solver['candidate_history'])
        self.assertEqual('no_eligible_candidate', solver['best_effort']['status'])
        self.assertIsNone(solver['best_effort']['selected_candidate_id'])
        self.assertEqual(1, len(self.outbound))
        for mode in ('star_reference', 'star_best_effort'):
            response = self.client.post('/api/agent/jobs', json={
                'message': '1+1', 'session_id': self.session, 'solver_mode': mode},
                headers=self.headers())
            self.assertEqual(503, response.status_code)
            self.assertEqual('star_prerequisites_unverified', response.get_json()['code'])
        self.assertEqual(200, self.client.get(f'/api/agent/jobs/{job_id}/candidate-replay').status_code)

    def test_traceback_excludes_complete_candidates_from_invalidated_dependencies(self):
        from tests.test_star_product_planning import FEATURES
        from tests.test_star_product_tools import NEED_PLAN, VERDICT
        from tests.test_star_product_traceback import PLAN, TRACE, report

        replies = [NEED_PLAN, PLAN]
        for text in ('safe answer', 'wrong answer', 'dependent answer', 'rejected answer'):
            replies += [report('private derivation', solution_candidate=text, answer_completeness='complete'),
                        TRACE if text == 'rejected answer' else VERDICT]
        self.open_star(replies, SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=10, max_http_attempts=10))
        job_id, job = self.start_best_effort()
        self.assertEqual('safe answer', job['result']['final_response'])
        solver = job['result']['solver']
        latest = {r['answer_text']: r for r in solver['candidate_history']}
        self.assertEqual('locally_reviewed', latest['safe answer']['review_state'])
        for text in ('wrong answer', 'dependent answer', 'rejected answer'):
            self.assertEqual('invalidated', latest[text]['review_state'])
            self.assertFalse(latest[text]['selection_eligible'])
            self.assertIn(latest[text]['candidate_id'], solver['best_effort']['excluded_candidate_ids'])
        replay = self.client.get(f'/api/agent/jobs/{job_id}/candidate-replay').get_json()
        self.assertTrue(replay['audit']['matches_persisted_decision'])
        self.assertEqual(10, len(self.outbound))
        self.assertEqual(0, job['result']['budget']['tool_calls'])

    def test_deadline_finalizes_only_persisted_candidates_and_retains_late_unknown(self):
        import time

        def late_polish(_request):
            time.sleep(1.1)
            return {'solution_candidate': 'late answer must not become candidate'}

        self.open_star([SOLVED, late_polish], SHOWCASE_STAR_BUDGET=RunBudgetLimits(
            max_model_calls=8, max_http_attempts=8, max_runtime_seconds=1))
        job_id, job = self.start_best_effort()
        self.assertEqual('2', job['result'].get('final_response'), job)
        solver = job['result']['solver']
        self.assertEqual('runtime_budget_exhausted', solver['best_effort']['termination_reason'])
        self.assertEqual(['2'], [v['answer_text'] for v in solver['candidate_history']])
        self.assertEqual(2, len(self.outbound))
        self.assertEqual('needs_review', solver['recovery']['status'])
        self.assertTrue(self.client.get(
            f'/api/agent/jobs/{job_id}/candidate-replay').get_json()['audit']['matches_persisted_decision'])

    def test_http_attempt_budget_stops_before_polish_and_selects_without_dispatch(self):
        self.open_star([SOLVED], SHOWCASE_STAR_BUDGET=RunBudgetLimits(
            max_model_calls=8, max_http_attempts=1, max_tool_calls=0))
        _, job = self.start_best_effort()
        self.assertEqual('2', job['result']['final_response'])
        self.assertEqual('http_attempt_budget_exhausted',
            job['result']['solver']['best_effort']['termination_reason'])
        self.assertEqual(1, len(self.outbound))
        self.assertEqual(1, job['result']['budget']['logical_calls'])

    def test_token_admission_failure_is_a_budget_result_without_provider_call(self):
        self.open_star([], SHOWCASE_STAR_BUDGET=RunBudgetLimits(
            max_model_calls=8, max_http_attempts=8, max_tokens=1))
        _, job = self.start_best_effort()
        self.assertEqual('partial_budget_exhausted', job['result']['solver']['status'])
        self.assertEqual('no_eligible_candidate', job['result']['solver']['best_effort']['status'])
        self.assertEqual([], self.outbound)
        self.assertEqual('safe', job['result']['solver']['recovery']['status'])
