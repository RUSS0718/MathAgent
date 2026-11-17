import tempfile
import unittest
from pathlib import Path
from showcase.solver_harness import SolverHarness


class PlanSourceTest(unittest.TestCase):
    def test_invalid_plan_rolls_back_and_next_valid_save_succeeds(self):
        from showcase.solver_harness.storage import SolverPersistenceError
        folder = self.enterContext(tempfile.TemporaryDirectory())
        h = SolverHarness(database_path=Path(folder) / 'rollback.sqlite', config={})
        self.addCleanup(h.close)
        before = h.solve('test', {'run_id': 'rollback-test'})
        with self.assertRaises(SolverPersistenceError):
            h.commit_event('rollback-test', expected_revision=0,
                event={'event_id': 'bad', 'type': 'initial_plan_generated'},
                state_updates={'plan_version': 1, 'plan': {'version': 1, 'steps': [None]}})
        self.assertFalse(h._showcase_store._connection.in_transaction)
        self.assertEqual(before, h.get_run('rollback-test'))
        saved = h.commit_event('rollback-test', expected_revision=0,
            event={'event_id': 'valid', 'type': 'initial_plan_generated'},
            state_updates={'plan_version': 1, 'plan': {'version': 1, 'steps': [
                {'step_id': 's1', 'title': '目标', 'objective': '验证', 'depends_on': []}]}})
        self.assertEqual(1, saved['state_revision'])
        self.assertEqual(1, len(saved['state']['role_stage_results']))

    def test_normal_save_retains_exact_source_across_status_events(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        if folder:
            h = SolverHarness(database_path=Path(folder) / 'test.sqlite', config={})
            self.addCleanup(h.close)
            run = h.solve('test', {'run_id': 'source-test'})
            run = h.commit_event(run['run_id'], expected_revision=0,
                event={'event_id': 'plan-1', 'type': 'initial_plan_generated'},
                state_updates={'plan_version': 1, 'plan': {'version': 1, 'steps': [
                    {'step_id': 'private-step', 'title': '平方非负', 'objective': r'对任意实数 x，(x-1)^2≥0', 'depends_on': []}]}})
            self.assertEqual(1, len(run['state']['role_stage_results']))
            saved = run['state']['role_stage_results'][0]
            self.assertEqual(saved['source_ref'], run['events'][-1]['role_stage_source'])
            run = h.commit_event(run['run_id'], expected_revision=1,
                event={'event_id': 'status', 'type': 'status_changed'}, state_updates={'phase': 'VERIFY'})
            self.assertEqual(saved, run['state']['role_stage_results'][0])

class PlanReadTest(unittest.TestCase):
    def setUp(self):
        from showcase.flask_app import create_app
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.app = create_app({'TESTING': True, 'SHOWCASE_DATA_DIR': folder, 'SHOWCASE_WORKER_ENABLED': False})
        for name in ('loopback_store', 'showcase_workspace_service', 'showcase_run_service'):
            self.addCleanup(self.app.extensions[name].close)
        self.client = self.app.test_client()
        csrf = self.client.get('/api/check_auth').json['csrf_token']
        headers = {'X-CSRF-Token': csrf, 'Idempotency-Key': '00000000-0000-4000-8000-000000000200'}
        session = self.client.post('/api/new_chat', headers=headers).json['new_session_id']
        self.job_id = self.client.post('/api/agent/jobs', headers=headers, json={'session_id': session, 'message': 'test'}).json['job_id']
        service = self.app.extensions['showcase_workspace_service']
        service.store._connection.execute("UPDATE workspace_jobs SET status='running' WHERE job_id=?", (self.job_id,))
        service.store._connection.commit()
        h = SolverHarness(database_path=service.store.database_path, config={})
        self.addCleanup(h.close)
        h.solve('test', {'run_id': self.job_id})
        h.commit_event(self.job_id, expected_revision=0, event={'event_id': 'p1', 'type': 'initial_plan_generated'},
            state_updates={'plan_version': 1, 'plan': {'version': 1, 'steps': [
                {'step_id': 'private', 'title': '平方非负', 'objective': '对任意实数 x，(x-1)^2≥0', 'depends_on': [], 'argument': 'PRIVATE'},
                {'step_id': 'secret', 'title': 'secret: PRIVATE MANY WORDS', 'objective': '目标', 'depends_on': ['private']}]}})
        self.h = h
        self.url = f'/api/agent/jobs/{self.job_id}/role-results/planner'

    def test_rewritten_old_identity_or_reference_never_publishes(self):
        import copy
        import json
        store = self.app.extensions['showcase_workspace_service'].store
        run = self.h.commit_event(self.job_id, expected_revision=1,
            event={'event_id': 'p2', 'type': 'plan_replaced'},
            state_updates={'plan_version': 2, 'plan': {'version': 2, 'steps': [
                {'step_id': 'new', 'title': '新计划', 'objective': '新目标', 'depends_on': []}]}})
        state = run['state']
        old_ref = state['role_stage_results'][0]['source_ref']
        self.assertEqual('replaced', self.client.get(self.url + '?source=' + old_ref).json['results'][0]['validity'])
        for key, value in (('plan_version', 2), ('attempt_index', 1),
                           ('specification_version', 'tampered'), ('event_id', 'different'),
                           ('source_ref', 'f' * 64)):
            with self.subTest(key=key):
                damaged = copy.deepcopy(state)
                damaged['role_stage_results'][0][key] = value
                store._connection.execute('UPDATE solver_states SET state_json=? WHERE run_id=?',
                    (json.dumps(damaged), self.job_id))
                store._connection.commit()
                ref = damaged['role_stage_results'][0]['source_ref']
                self.assertEqual('unavailable', self.client.get(self.url + '?source=' + ref).json['content_status'])

    def test_storage_identity_conflicts_are_unavailable_without_recovery_or_writes(self):
        from unittest.mock import patch
        store = self.app.extensions['showcase_workspace_service'].store
        row = store._connection.execute('SELECT * FROM solver_states WHERE run_id=?', (self.job_id,)).fetchone()
        for column, value in (('problem_hash', 'wrong'), ('config_hash', 'wrong'), ('state_revision', 99)):
            with self.subTest(column=column):
                store._connection.execute(f'UPDATE solver_states SET {column}=? WHERE run_id=?', (value, self.job_id))
                store._connection.commit()
                before = '\n'.join(store._connection.iterdump())
                with patch.object(SolverHarness, 'get_run', side_effect=AssertionError('no reconciliation')):
                    self.assertEqual('unavailable', self.client.get(self.url).json['content_status'])
                self.assertEqual(before, '\n'.join(store._connection.iterdump()))
                store._connection.execute(f'UPDATE solver_states SET {column}=? WHERE run_id=?', (row[column], self.job_id))
                store._connection.commit()

    def test_ordinary_owner_reads_exact_saved_source_without_business_writes(self):
        from unittest.mock import patch
        store = self.app.extensions['showcase_workspace_service'].store
        before = '\n'.join(store._connection.iterdump())
        state_before = self.h.get_run(self.job_id)
        with patch('requests.sessions.Session.request', side_effect=AssertionError('no outbound')):
            response = self.client.get(self.url)
            self.assertEqual(200, response.status_code)
            body = response.json
            self.assertEqual('published', body['content_status'])
            result = body['results'][0]
            self.assertEqual('对任意实数 x，(x-1)^2≥0', result['items'][0]['objective'])
            self.assertEqual('[redacted]', result['items'][1]['title'])
            self.assertEqual('plan_structure', result['check']['scope'])
            self.assertEqual(result['body_version'], result['check']['body_version'])
            for _ in range(3):
                self.assertEqual(body, self.client.get(self.url + '?source=' + result['source_ref']).json)
            self.assertEqual('unavailable', self.client.get(self.url + '?source=wrong').json['content_status'])
        self.assertNotIn('PRIVATE', response.text)
        state_after = self.h.get_run(self.job_id)
        for field in ('plan', 'role_stage_results', 'calls', 'counters', 'budget'):
            self.assertEqual(state_before['state'].get(field), state_after['state'].get(field))
        self.assertEqual(state_before['events'], state_after['events'])
        self.assertEqual(before, '\n'.join(store._connection.iterdump()))
        self.assertEqual(403, self.client.get(f'/api/agent/jobs/{self.job_id}/report').status_code)

    def test_auth_and_legacy_never_fall_back(self):
        self.assertEqual(401, self.app.test_client().get(self.url).status_code)
        other = self.app.test_client()
        other.get('/api/check_auth')
        service = self.app.extensions['showcase_workspace_service']
        foreign_session = service.create_session('different-owner')
        foreign, _ = service.create_job(user_id='different-owner', session_id=foreign_session,
            problem='test', idempotency_key='00000000-0000-4000-8000-000000000201')
        self.assertEqual(404, other.get(f"/api/agent/jobs/{foreign['job_id']}/role-results/planner").status_code)
        run = self.h.get_run(self.job_id)
        self.h.commit_event(self.job_id, expected_revision=run['state_revision'],
            event={'event_id': 'attempt', 'type': 'status_changed'}, state_updates={'attempt_index': 1})
        self.assertEqual('unavailable', self.client.get(self.url).json['content_status'])


    def test_empty_corrupt_and_cross_job_sources_are_unavailable(self):
        import copy
        import json
        store = self.app.extensions['showcase_workspace_service'].store
        state = self.h.get_run(self.job_id)['state']
        for query in ('?source=', '?source=broken'):
            self.assertEqual('unavailable', self.client.get(self.url + query).json['content_status'])
        for mutate in (
            lambda s: s.update(run_id='different-job'),
            lambda s: s.update(role_stage_results=[None]),
            lambda s: s['role_stage_results'][0].update(items=None),
            lambda s: s['role_stage_results'][0].update(check=None),
            lambda s: s['role_stage_results'][0].update(plan_version='1'),
        ):
            damaged = copy.deepcopy(state)
            mutate(damaged)
            store._connection.execute('UPDATE solver_states SET state_json=? WHERE run_id=?',
                (json.dumps(damaged), self.job_id))
            store._connection.commit()
            response = self.client.get(self.url)
            self.assertEqual(200, response.status_code)
            self.assertEqual('unavailable', response.json['content_status'])

    def test_bound_body_and_check_conflicts_do_not_publish(self):
        import copy
        import json
        store = self.app.extensions['showcase_workspace_service'].store
        state = self.h.get_run(self.job_id)['state']
        ref = state['role_stage_results'][0]['source_ref']
        for change in ('body', 'check', 'duplicate'):
            damaged = copy.deepcopy(state)
            r = damaged['role_stage_results'][0]
            if change == 'body':
                r['items'][0]['objective'] = 'wrong body'
            elif change == 'check':
                r['check']['body_version'] = 'wrong version'
            else:
                damaged['role_stage_results'].append(copy.deepcopy(r))
            store._connection.execute('UPDATE solver_states SET state_json=? WHERE run_id=?',
                (json.dumps(damaged), self.job_id))
            store._connection.commit()
            self.assertEqual('unavailable', self.client.get(self.url + '?source=' + ref).json['content_status'])
