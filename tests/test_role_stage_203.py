import copy
import unittest
from showcase.role_stage_results import save_role_sources, role_results


class HistoricalResultsTest(unittest.TestCase):
    def setUp(self):
        self.state = dict(run_id='run-A', run_salt='secret', problem_hash='problem',
                          specification_version=1, plan_version=1, attempt_index=0)

    def save(self, text, event_id, binding=None):
        publication = dict(role='reasoner', stage='step', sections=[dict(label='结论', text=text)],
                           check=dict(scope='step', status='unreviewed', label='步骤候选，未检查'),
                           binding=binding or dict(kind='step_report', step_id='s1', report_call_id=event_id))
        updates, event = save_role_sources(self.state, {}, dict(type='step_reported', event_id=event_id),
                                           collectors=[lambda state, event: [publication]])
        self.state.update(updates)
        return event['role_stage_source']

    def test_exact_history_and_metadata_have_no_latest_body_fallback(self):
        a = self.save('对任意实数 x，(x-1)^2≥0', 'A')
        b = self.save('对任意实数 x，x^2≥0', 'B')
        old = role_results(self.state, 'reason_noncoding', a)
        self.assertEqual('对任意实数 x，(x-1)^2≥0', old['results'][0]['sections'][0]['text'])
        self.assertEqual('replaced', old['results'][0]['validity'])
        self.assertEqual([b], [r['source_ref'] for r in role_results(self.state, 'reasoner')['results']])
        self.assertTrue(all('sections' not in r for r in old['history']))
        for source in ('', 'bad', 'f' * 64):
            self.assertEqual('unavailable', role_results(self.state, 'reasoner', source)['content_status'])

    def test_content_check_binding_and_identity_tampering_fail_closed(self):
        ref = self.save('对任意实数 x，x^2≥0', 'A')
        original = copy.deepcopy(self.state)
        for field, value in [('sections', [dict(label='结论', text='伪造')]),
                             ('check', dict(scope='whole', status='accepted')),
                             ('binding', dict(kind='step_report', step_id='other')),
                             ('run_id', 'foreign'), ('role', 'explore'), ('event_id', 'changed')]:
            with self.subTest(field=field):
                self.state = copy.deepcopy(original)
                self.state['role_stage_results'][0][field] = value
                self.assertEqual('unavailable', role_results(self.state, 'reasoner', ref)['content_status'])
        self.state = copy.deepcopy(original)
        self.state['role_stage_results'].append(copy.deepcopy(self.state['role_stage_results'][0]))
        self.assertEqual('unavailable', role_results(self.state, 'reasoner', ref)['content_status'])

    def test_rescued_classified_result_survives_plan_change_but_dependency_revocation_invalidates(self):
        self.state['verified_results_ledger'] = [
            dict(result_id='dep', valid=True, invalidated=False, dependencies=[]),
            dict(result_id='outcome', valid=True, invalidated=False, dependencies=['dep'])]
        ref = self.save('局部引理', 'A', dict(kind='classified_result', result_id='outcome', dependencies=['dep']))
        self.state['plan_version'] = 2
        self.state['rescued_results'] = [self.state['verified_results_ledger'][1]]
        self.assertEqual('current', role_results(self.state, 'reasoner', ref)['results'][0]['validity'])
        self.state['verified_results_ledger'][0]['invalidated'] = True
        before = copy.deepcopy(self.state)
        for _ in range(3):
            self.assertEqual([], role_results(self.state, 'reasoner')['results'])
            old = role_results(self.state, 'reasoner', ref)['results'][0]
            self.assertEqual('invalidated', old['validity'])
            self.assertEqual('局部引理', old['sections'][0]['text'])
            self.assertEqual('unreviewed', old['check']['status'])
        self.assertEqual(before, self.state)

    def test_run_isolation_even_for_identical_saved_body(self):
        ref = self.save('x≥0', 'A')
        self.state['run_id'] = 'run-B'
        self.assertEqual('unavailable', role_results(self.state, 'reasoner', ref)['content_status'])


class HistoricalApiTest(unittest.TestCase):
    def setUp(self):
        from tests.test_role_stage_200 import PlanReadTest
        PlanReadTest.setUp(self)
        state = self.h.get_run(self.job_id)['state']
        publication = dict(role='reasoner', stage='step_submission',
                           sections=[dict(label='阶段主张', text='对任意实数 x，x²≥0')],
                           check=dict(scope='step_submission', status='unreviewed', label='步骤候选，待检查'),
                           binding=dict(kind='step_report', step_id='s1'))
        updates, event = save_role_sources(state, {}, dict(type='step_reported', event_id='finding-A'),
                                           collectors=[lambda state, event: [publication]])
        self.ref = event['role_stage_source']
        self.h.commit_event(self.job_id, expected_revision=state['state_revision'], event=event, state_updates=updates)
        self.url = f'/api/agent/jobs/{self.job_id}/role-results/reasoner'

    def test_failed_job_keeps_saved_results_and_get_is_read_only(self):
        from unittest.mock import patch
        from showcase.solver_harness import SolverHarness
        store = self.app.extensions['showcase_workspace_service'].store
        store._connection.execute("UPDATE workspace_jobs SET status='failed' WHERE job_id=?", (self.job_id,))
        store._connection.commit()
        before = '\n'.join(store._connection.iterdump())
        with patch.object(SolverHarness, 'get_run', side_effect=AssertionError('no recovery')):
            with patch('requests.sessions.Session.request', side_effect=AssertionError('no dispatch')):
                for _ in range(3):
                    for suffix in ('', '?source=' + self.ref):
                        response = self.client.get(self.url + suffix)
                        self.assertEqual('no-store', response.headers['Cache-Control'])
                        self.assertEqual('failed', response.json['status'])
                        self.assertEqual('current', response.json['results'][0]['validity'])
                        self.assertEqual('对任意实数 x，x²≥0', response.json['results'][0]['sections'][0]['text'])
                    for source in ('', 'bad', 'f' * 64):
                        self.assertEqual('unavailable', self.client.get(self.url + '?source=' + source).json['content_status'])
        self.assertEqual(before, '\n'.join(store._connection.iterdump()))

    def test_each_get_rechecks_owner_and_never_borrows_cross_job_source(self):
        self.assertEqual(200, self.client.get(self.url + '?source=' + self.ref).status_code)
        self.assertEqual(401, self.app.test_client().get(self.url).status_code)
        service = self.app.extensions['showcase_workspace_service']
        session = service.create_session('different-owner')
        foreign, _ = service.create_job(user_id='different-owner', session_id=session,
            problem='test', idempotency_key='00000000-0000-4000-8000-000000000203')
        self.assertEqual(404, self.client.get(f"/api/agent/jobs/{foreign['job_id']}/role-results/reasoner?source={self.ref}").status_code)
        service.store._connection.execute('UPDATE workspace_jobs SET user_id=? WHERE job_id=?', ('different-owner', self.job_id))
        service.store._connection.commit()
        self.assertEqual(404, self.client.get(self.url + '?source=' + self.ref).status_code)
