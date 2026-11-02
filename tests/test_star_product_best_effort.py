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

    def test_independent_counterexample_refutes_candidate_before_budget_selection(self):
        from tests.test_star_product_counterexample import (
            ACCEPT,
            FEATURES,
            FOUND,
            NEED_PLAN,
            PLAN,
            STEP,
        )

        self.open_star([NEED_PLAN, PLAN, {**STEP, 'solution_candidate': '0 is the minimum',
            'answer_completeness': 'complete'}, ACCEPT, FOUND],
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=5, max_http_attempts=5))
        _, job = self.start_best_effort()
        history = job['result']['solver']['candidate_history']
        self.assertEqual('refuted', history[-1]['review_state'])
        self.assertFalse(history[-1]['selection_eligible'])
        self.assertEqual('no_eligible_candidate', job['result']['solver']['best_effort']['status'])
        self.assertNotEqual('0 is the minimum', job['result']['final_response'])
        self.assertEqual(5, len(self.outbound))

    def test_reopened_job_and_replay_are_immutable_and_do_not_dispatch(self):
        import json

        from showcase.flask_app import create_app

        self.open_star([SOLVED], SHOWCASE_STAR_BUDGET=RunBudgetLimits(
            max_model_calls=1, max_http_attempts=1, max_tool_calls=0))
        job_id, job = self.start_best_effort()
        original = self.client.get(f'/api/agent/jobs/{job_id}/candidate-replay').get_json()
        app = create_app({'TESTING': True, 'SHOWCASE_DATA_DIR': self.data_dir})
        for name in ('loopback_store', 'showcase_run_service', 'showcase_workspace_service'):
            self.addCleanup(app.extensions[name].close)
        with app.test_client() as client:
            client.get('/api/check_auth')
            self.assertEqual(original, client.get(
                f'/api/agent/jobs/{job_id}/candidate-replay').get_json())
            reopened = client.get(f'/api/agent/jobs/{job_id}').get_json()
            self.assertEqual(job['result']['solver'], reopened['result']['solver'])
            evidence = client.get(f'/api/runs/{job_id}/evidence').get_json()
            public = json.dumps(evidence)
            for forbidden in ('prompt_layers', 'session_history', 'role_context',
                              'selected_source_record', 'request_hash', 'owner_instance',
                              'problem_hash', 'probability'):
                self.assertNotIn(forbidden, public)
            record = reopened['result']['solver']['candidate_history'][0]
            self.assertEqual({'version', 'answer_text', 'answer_hash', 'source_phase',
                'plan_version', 'attempt_index', 'answer_completeness', 'review_state',
                'selection_eligible', 'candidate_id', 'step_refs', 'dependency_refs',
                'source_event_refs', 'evidence_refs', 'invalidated_by', 'evidence_grade'}, set(record))
        self.assertEqual(1, len(self.outbound))
        self.assertEqual(404, self.client.get(
            '/api/agent/jobs/unknown/candidate-replay').status_code)

    def test_rewritten_best_effort_delivery_cannot_inherit_selected_artifact(self):
        from unittest.mock import patch

        self.open_star([SOLVED], SHOWCASE_STAR_BUDGET=RunBudgetLimits(
            max_model_calls=1, max_http_attempts=1, max_tool_calls=0))
        with patch('showcase.star_product_pipeline.export_result',
                   return_value={'final_response': 'unreviewed rewrite'}):
            job_id, job = self.start_best_effort()
        check = self.report(job_id)['checks']
        self.assertEqual('artifact_changed', check['binding'])
        self.assertNotEqual(check['artifact'], check['selection']['artifact'])
        self.assertEqual('needs_review', check['acceptance'])
        self.assertEqual('failed', job['status'])
        self.assertEqual(1, len(self.outbound))

    def test_selector_bypass_is_detected_by_the_public_refutation_contract(self):
        from unittest.mock import patch

        from showcase.solver_harness.best_effort import select_best_effort
        from tests.test_star_product_counterexample import (
            ACCEPT,
            FEATURES,
            FOUND,
            NEED_PLAN,
            PLAN,
            STEP,
        )

        def bypass(snapshot):
            decision = select_best_effort(snapshot)
            record = snapshot['candidate_registry'][0]
            return {**decision, 'status': 'candidate_selected',
                    'selected_candidate_id': record['candidate_id'], 'selected_source_record': record}

        self.open_star([NEED_PLAN, PLAN, {**STEP, 'solution_candidate': 'refuted minimum',
            'answer_completeness': 'complete'}, ACCEPT, FOUND],
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=5, max_http_attempts=5))
        with patch('showcase.solver_harness.best_effort.select_best_effort', side_effect=bypass):
            _, job = self.start_best_effort()
        with self.assertRaises(AssertionError):
            self.assertEqual('no_eligible_candidate', job['result']['solver']['best_effort']['status'])
        self.assertEqual('refuted minimum', job['result']['final_response'])
        self.assertEqual(5, len(self.outbound))

    def test_cancel_beats_expired_pure_selection_and_cannot_publish_late_candidate(self):
        import time

        holder = {}

        def cancel_then_late(_request):
            self.cancel(holder['job_id'])
            time.sleep(1.1)
            return {'solution_candidate': 'late canceled answer'}

        self.open_star([SOLVED, cancel_then_late], SHOWCASE_STAR_BUDGET=RunBudgetLimits(
            max_model_calls=8, max_http_attempts=8, max_runtime_seconds=1))
        response = self.client.post('/api/agent/jobs', json={
            'message': '1+1', 'session_id': self.session,
            'solver_mode': 'star_limited_best_effort'}, headers=self.headers())
        holder['job_id'] = response.get_json()['job_id']
        job = self.terminal(holder['job_id'])
        self.assertEqual('canceled', job['status'])
        self.wait_for(lambda: len(self.outbound) == 2)
        solver = self.job(holder['job_id'])['result']['solver']
        self.assertIsNone(solver['best_effort'])
        self.assertEqual(['2'], [v['answer_text'] for v in solver['candidate_history']])

    def test_tool_ceiling_allows_answer_without_forcing_best_effort_selection(self):
        from copy import deepcopy

        from showcase.tools import ToolRegistry
        from tests.star_product_support import ACCEPT
        from tests.test_star_product_tools import FEATURES, NEED_PLAN, PLAN, STEP, VERDICT

        actual = []
        registry = ToolRegistry()
        registry.register('polynomial_check', lambda args: actual.append(args) or 2)
        step = deepcopy(STEP)
        step['claims'].append(deepcopy(step['claims'][0]))
        self.open_star([NEED_PLAN, PLAN, step, VERDICT, {'final_response': '1+1=2'}, ACCEPT], SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_REGISTRY=registry,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8,
                                                max_tool_calls=1))
        _, job = self.start_best_effort()
        self.assertEqual([{}], actual)
        self.assertEqual(6, len(self.outbound))
        self.assertEqual(1, job['result']['budget']['tool_calls'])
        self.assertEqual('succeeded', job['status'])
        self.assertEqual('1+1=2', job['result']['final_response'])
        self.assertIsNone(job['result']['solver']['best_effort'])
