"""View requests stay read-only while an independently saved result arrives."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from showcase.flask_app import create_app
from showcase.solver_harness import SolverHarness


class BackgroundAttributionTest(unittest.TestCase):
    def test_reads_and_prearranged_background_commit_have_separate_attribution(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": folder,
                          "SHOWCASE_WORKER_ENABLED": False})
        for name in ("loopback_store", "showcase_workspace_service", "showcase_run_service"):
            self.addCleanup(app.extensions[name].close)
        client = app.test_client()
        csrf = client.get('/api/check_auth').json['csrf_token']
        headers = {'X-CSRF-Token': csrf, 'Idempotency-Key': '00000000-0000-4000-8000-000000000199'}
        session = client.post('/api/new_chat', headers=headers).json['new_session_id']
        job = client.post('/api/agent/jobs', headers=headers,
                          json={'session_id': session, 'message': 'controlled fixture'}).json['job_id']
        store = app.extensions['showcase_workspace_service'].store
        store.start_job(job, execution_mode='fake')
        harness = SolverHarness(database_path=Path(store.database_path), config={})
        self.addCleanup(harness.close)
        harness.solve('controlled fixture', {'run_id': job})
        url = f'/api/agent/jobs/{job}/role-results/planner'

        def background_save(version):
            return harness.commit_event(job, expected_revision=version - 1,
                event={'event_id': f'prearranged-background-{version}',
                       'type': 'initial_plan_generated' if version == 1 else 'plan_replaced'},
                state_updates={'plan_version': version, 'plan': {'version': version, 'steps': [
                    {'step_id': f's{version}', 'title': f'保存目标 {version}',
                     'objective': f'完整数学条件 {version}', 'depends_on': []}]}})

        def business_snapshot():
            # Same connection, no session heartbeat table: view attribution only.
            tables = ('workspace_jobs', 'workspace_events', 'runs', 'events',
                      'solver_states', 'solver_events', 'run_budgets')
            return {table: [tuple(row) for row in store._connection.execute(
                f'SELECT * FROM "{table}" ORDER BY rowid')] for table in tables}

        with patch('requests.sessions.Session.request', side_effect=AssertionError('no provider HTTP')):
            first = background_save(1)
            source = first['events'][-1]['role_stage_source']
            before = business_snapshot()
            for _ in range(3):
                self.assertEqual('published', client.get(url).json['content_status'])
                self.assertEqual(1, client.get(url + '?source=' + source).json['results'][0]['plan_version'])
            self.assertEqual(before, business_snapshot())

            # This single explicit normal commit represents the already-arranged
            # background producer. No view request invokes it or creates a call.
            second = background_save(2)
            self.assertEqual(first['state_revision'] + 1, second['state_revision'])
            self.assertEqual(len(first['events']) + 1, len(second['events']))
            self.assertEqual('prearranged-background-2', second['events'][-1]['event_id'])
            for field in ('calls', 'counters', 'budget', 'deadline_at'):
                self.assertEqual(first['state'].get(field), second['state'].get(field))
            after_background = business_snapshot()
            self.assertNotEqual(before['solver_states'], after_background['solver_states'])
            for _ in range(3):
                old = client.get(url + '?source=' + source).json['results'][0]
                self.assertEqual(1, old['plan_version'])
                self.assertEqual('replaced', old['validity'])
                self.assertEqual(2, client.get(url).json['results'][0]['plan_version'])
            self.assertEqual(after_background, business_snapshot())
