"""Final review regressions at the authorized save and public GET seams."""
import copy
import json
import unittest
from unittest.mock import patch

from showcase.role_stage_results import role_results, save_committed_sources
from showcase.solver_harness import SolverHarness
from showcase.solver_harness.sessions import prepare_session
from tests.test_role_stage_201 import fixture
from tests.test_role_stage_202 import step_state


class SavedFindingsTest(unittest.TestCase):
    def test_saved_step_verdicts_keep_exact_source_and_check_binding(self):
        state, event = step_state()
        state.update(problem_hash='problem', run_salt='salt', verified_results_ledger=[])
        refs = []
        for index, (valid, verdict, expected) in enumerate([
                (True, 'ACCEPT', 'accepted'), (True, 'CHALLENGE', 'rejected'),
                (False, 'ACCEPT', 'unknown')]):
            verification = state['steps']['s1']['verification']
            verification.update(valid=valid, verdict=verdict, objection='')
            state['calls']['review']['response'].update(verification)
            event.update(verification, event_id=f'review-{index}')
            updates, saved = save_committed_sources(state, {}, event)
            state.update(updates)
            refs.append((saved['role_stage_source'], expected))
        for source, expected in refs:
            result, = role_results(state, 'step_verifier', source)['results']
            self.assertEqual(source, result['source_ref'])
            self.assertEqual(expected, result['check']['status'])
            self.assertEqual(result['body_version'], result['check']['body_version'])
            self.assertEqual('step_model_review', result['check']['scope'])

    def test_research_through_actual_persistent_session_save(self):
        from showcase.solver_harness import ScriptedModelPort
        config = {'features': {'persistent_sessions': True, 'stream_recovery': True}}
        with SolverHarness(config=config) as harness:
            run = harness.solve('prove', {'run_id': 'native-research'})
            task_id = 'replan1:task0'
            run = harness.commit_event(run['run_id'], expected_revision=run['state_revision'],
                event={'event_id': 'seed', 'type': 'fixture_loaded'},
                state_updates={'plan_version': 1, 'specification_version': 1})
            logical = f"research:{run['run_id']}:{task_id}"
            port = ScriptedModelPort([{'findings': ['x²≥0，x为实数']}])
            harness.dispatch(run, port.complete, {'run_id': run['run_id'], 'call_id': 'research-call',
                'role': 'researcher', 'session_key': logical, 'problem_spec_version': 1})
            run = harness.get_run(run['run_id'])
            run = harness.commit_event(run['run_id'], expected_revision=run['state_revision'],
                event={'event_id': 'research-save', 'type': 'reexploration_completed'},
                state_updates={'reexploration_tasks': [dict(task_id=task_id, status='complete', output_ref=task_id)],
                    'reexploration_findings': [dict(task_id=task_id, output={'findings': ['x²≥0，x为实数']})]})
            state = run['state']
            self.assertIn(port.requests[0]['session_key'], state['session_registry'])
            result = role_results(state, 'researcher')
            self.assertEqual('published', result['content_status'])
            self.assertEqual('x²≥0，x为实数', result['results'][0]['sections'][0]['text'])
            self.assertEqual('unreviewed', result['results'][0]['check']['status'])

    def test_native_research_session_publishes_only_exact_task_source(self):
        state, event = fixture('researcher')
        state.update(run_salt='salt', config_hash='config', current_step=None, updated_at='now')
        logical = 'research:run-a:task-a'
        state['reexploration_tasks'] = [dict(task_id='task-a', status='complete', output_ref='task-a')]
        state['reexploration_findings'] = [dict(task_id='task-a', output={'findings': ['x²≥0，x为实数']})]
        _, prepared = prepare_session({'state': state}, dict(role='researcher', call_id='call-a', session_key=logical))
        state['calls']['call-a'].update(session_key=prepared['session_key'], response={'findings': ['x²≥0，x为实数']})
        event['type'] = 'reexploration_completed'
        updates, saved = save_committed_sources(state, {}, event)
        result = role_results({**state, **updates}, 'researcher')
        self.assertEqual('published', result['content_status'])
        self.assertEqual(saved['role_stage_source'], result['results'][0]['source_ref'])
        self.assertEqual('unreviewed', result['results'][0]['check']['status'])
        for field, value in [('session_key', prepared['session_key'] + ':other'), ('run_id', 'foreign'),
                             ('plan_version', 2), ('problem_hash', 'foreign')]:
            with self.subTest(field=field):
                wrong = copy.deepcopy(state)
                wrong['calls']['call-a'][field] = value
                self.assertNotIn('role_stage_source', save_committed_sources(wrong, {}, event)[1])

    def test_saved_private_report_is_distinct_from_idle_empty(self):
        from showcase.solver_harness.step import _normalize_report
        from showcase.solver_harness.intern_schemas import response_schema
        from showcase.tool_schemas import schema_error
        state, event = fixture('reasoner')
        self.assertEqual('empty', role_results(state, 'reasoner')['content_status'])
        step = dict(step_id='s', objective='目标')
        reply = dict(argument='PRIVATE argument', claims=[], blocked=True)
        self.assertIsNone(schema_error(reply, response_schema({'role': 'reasoner'})))
        state['steps'] = {'s': {'report': _normalize_report(reply, step), 'status': 'VERIFYING'}}
        state['calls']['call-a'].update(response=reply, request={'step': step, 'problem_spec_version': 1})
        event.update(type='step_reported', step_id='s')
        updates, saved = save_committed_sources(state, {}, event)
        state.update(updates)
        for source in (None, saved.get('role_stage_source')):
            result = role_results(state, 'reasoner', source)
            self.assertEqual('not_published', result['content_status'])
            self.assertEqual([], result['results'])
            self.assertNotIn('PRIVATE', json.dumps(result))


class SaveAndReadTest(unittest.TestCase):
    def setUp(self):
        from tests.test_role_stage_200 import PlanReadTest
        PlanReadTest.setUp(self)

    def save_review(self):
        base = self.h.get_run(self.job_id)
        extra, event = step_state()
        extra['calls']['review']['run_id'] = self.job_id
        for key in ('run_id', 'plan', 'specification_version', 'plan_version', 'attempt_index'):
            extra.pop(key, None)
        return self.h.commit_event(self.job_id, expected_revision=base['state_revision'], event=event, state_updates=extra)

    def test_saved_private_report_public_get_and_idle_empty_remain_distinct(self):
        from showcase.solver_harness.step import _normalize_report
        url = f'/api/agent/jobs/{self.job_id}/role-results/reasoner'
        self.assertEqual('empty', self.client.get(url).json['content_status'])
        base = self.h.get_run(self.job_id)
        state, event = fixture('reasoner')
        step = dict(step_id='s', objective='目标')
        reply = dict(argument='PRIVATE report', claims=[], blocked=True)
        state['calls']['call-a'].update(run_id=self.job_id, problem_hash=base['state']['problem_hash'],
            response=reply, request={'step': step, 'problem_spec_version': 1})
        event.update(type='step_reported', step_id='s')
        saved = self.h.commit_event(self.job_id, expected_revision=base['state_revision'], event=event,
            state_updates={'specification_version': 1, 'calls': state['calls'],
                'steps': {'s': {'report': _normalize_report(reply, step), 'status': 'VERIFYING'}}})
        ref = saved['events'][-1]['role_stage_source']
        for suffix in ('', '?source=' + ref):
            response = self.client.get(url + suffix)
            self.assertEqual('not_published', response.json['content_status'])
            self.assertEqual([], response.json['results'])
            self.assertNotIn('PRIVATE', response.get_data(as_text=True))

    def test_null_call_is_rejected_and_unexpected_producer_exception_rolls_back(self):
        from showcase.role_stage_reviews import collect
        state, event = step_state()
        state['calls']['review'] = None
        self.assertEqual([], collect(state, event))
        before = self.h.get_run(self.job_id)
        with patch('showcase.role_stage_reviews.collect', side_effect=RuntimeError('producer failed')):
            with self.assertRaises(RuntimeError):
                self.h.commit_event(self.job_id, expected_revision=before['state_revision'],
                    event={'event_id': 'exception', 'type': 'status_changed'}, state_updates={'phase': 'VERIFY'})
        self.assertFalse(self.h._showcase_store._connection.in_transaction)
        self.assertEqual(before, self.h.get_run(self.job_id))
        saved = self.h.commit_event(self.job_id, expected_revision=before['state_revision'],
            event={'event_id': 'next', 'type': 'status_changed'}, state_updates={'phase': 'VERIFY'})
        self.assertEqual(before['state_revision'] + 1, saved['state_revision'])

    def test_damaged_step_repeated_get_is_unavailable_without_writes_or_dispatch(self):
        saved = self.save_review()
        ref = saved['events'][-1]['role_stage_source']
        url = f'/api/agent/jobs/{self.job_id}/role-results/step_verifier'
        self.assertEqual('rejected', self.client.get(url).json['results'][0]['check']['status'])
        store = self.app.extensions['showcase_workspace_service'].store
        state = saved['state']
        state['steps']['s1'] = None
        store._connection.execute('UPDATE solver_states SET state_json=? WHERE run_id=?', (json.dumps(state), self.job_id))
        store._connection.commit()
        before = '\n'.join(store._connection.iterdump())
        with patch.object(SolverHarness, 'get_run', side_effect=AssertionError('no recovery')), \
             patch('requests.sessions.Session.request', side_effect=AssertionError('no dispatch')):
            for _ in range(3):
                for suffix in ('', '?source=' + ref):
                    response = self.client.get(url + suffix)
                    self.assertEqual(200, response.status_code)
                    self.assertEqual('unavailable', response.json['content_status'])
        self.assertEqual(before, '\n'.join(store._connection.iterdump()))
