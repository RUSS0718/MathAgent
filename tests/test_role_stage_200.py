import tempfile
import unittest
from pathlib import Path
from showcase.solver_harness import SolverHarness


class PlanSourceTest(unittest.TestCase):
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

    def test_ordinary_owner_reads_exact_saved_source_without_business_writes(self):
        from unittest.mock import patch
        store = self.app.extensions['showcase_workspace_service'].store
        before = '\n'.join(store._connection.iterdump())
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

