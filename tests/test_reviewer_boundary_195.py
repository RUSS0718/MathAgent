"""HTTP contracts for session-scoped reviewer admission."""
import tempfile
import unittest

from showcase.flask_app import create_app


class ReviewerBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = {"TESTING": True, "SHOWCASE_DATA_DIR": self.tmp.name,
                       "SHOWCASE_WORKER_ENABLED": False, "SHOWCASE_FAITHFUL_INTERVENTION_ENABLED": True, "SHOWCASE_REVIEWER_SECRET": "test-review-secret"}
        self.apps = []
        self.app = self.make_app()
        self.client = self.app.test_client()
        self.csrf = self.client.get('/api/check_auth').json['csrf_token']

    def make_app(self):
        app = create_app(self.config)
        self.apps.append(app)
        return app

    def tearDown(self):
        for app in self.apps:
            for name in ('showcase_workspace_service', 'showcase_run_service', 'loopback_store'):
                app.extensions[name].close()
        self.tmp.cleanup()

    def grant(self, client=None, csrf=None, secret='test-review-secret'):
        return (client or self.client).post('/api/reviewer/grant', json={'secret': secret},
                headers={'X-CSRF-Token': csrf or self.csrf})

    def test_grant_is_csrf_protected_persistent_session_scoped_and_revocable(self):
        other = self.app.test_client()
        other.get('/api/check_auth')
        self.assertEqual(403, self.client.post('/api/reviewer/grant', json={'secret':'test-review-secret'}).status_code)
        self.assertEqual(403, self.grant(secret='wrong').status_code)
        self.assertEqual(401, self.app.test_client().post('/api/reviewer/grant',
            json={'secret':'test-review-secret'}).status_code)
        self.assertEqual(403, self.client.post('/api/reviewer/grant',
            json={'secret':'test-review-secret'}, headers={'X-CSRF-Token':'wrong'}).status_code)
        self.assertNotIn('test-review-secret',self.client.get('/api/capabilities').text)
        self.assertEqual(200, self.grant().status_code)
        self.assertIn('reviewer.access', self.client.get('/api/check_auth').json['permissions'])
        self.assertNotIn('reviewer.access', other.get('/api/check_auth').json['permissions'])
        restarted = self.make_app().test_client()
        restarted.set_cookie('auth_session', self.client.get_cookie('auth_session').value)
        self.assertIn('reviewer.access', restarted.get('/api/check_auth').json['permissions'])
        self.assertEqual(403, self.grant(secret='wrong').status_code)
        self.assertIn('reviewer.access', self.client.get('/api/check_auth').json['permissions'])
        self.client.post('/api/logout', headers={'X-CSRF-Token':self.csrf})
        self.assertNotIn('reviewer.access', restarted.get('/api/check_auth').json['permissions'])

    def test_technical_routes_deny_ordinary_and_allow_reviewer_dispatch(self):
        paths = ['/dashboard/system', '/dashboard/campaigns', '/dashboard/runs/old',
                 '/api/runs/old/events', '/api/agent/jobs/old/report',
                 '/api/agent/jobs/old/memory', '/api/agent/jobs/old/interventions',
                 '/api/faithful/runs', '/api/campaigns', '/api/debug']
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(401, self.app.test_client().get(path).status_code)
                self.assertEqual(403, self.client.get(path).status_code)
        self.assertEqual(200, self.grant().status_code)
        self.assertEqual(200, self.client.get('/dashboard/system').status_code)
        self.assertEqual(404, self.client.get('/api/agent/jobs/old/report').status_code)

    def test_no_secret_configuration_denies_even_testing(self):
        self.config['SHOWCASE_REVIEWER_SECRET'] = None
        client = self.make_app().test_client()
        csrf = client.get('/api/check_auth').json['csrf_token']
        self.assertEqual(403, self.grant(client, csrf).status_code)
        self.assertNotIn('reviewer.access', client.get('/api/check_auth').json['permissions'])

    def test_ordinary_job_and_replay_keep_plan_roles_without_nested_technical_data(self):
        headers = {'X-CSRF-Token':self.csrf}
        session = self.client.post('/api/new_chat', headers=headers).json['new_session_id']
        response = self.client.post('/api/agent/jobs', headers={**headers,'Idempotency-Key':'e65e1972-9557-4407-96a7-c7311d65a4ed'},
                                    json={'session_id':session,'message':'计算 1+1'})
        self.assertEqual(202, response.status_code)
        job = response.json['job_id']
        store = self.app.extensions['showcase_workspace_service'].store
        store.append_event(job, {'type':'solver_progress','solver_event_id':'fixture-plan-1','role':'planner','solver_event_type':'initial_plan_generated',
            'solver':{'phase':'PLAN','progress':{'plan_version':1,'steps':[{'label':'步骤 1',
            'goal_summary':'先计算和','current':True,'raw_metadata':{'internal':'DO_NOT_PUBLISH'}}],
            'budget':{'internal':'DO_NOT_PUBLISH'}}},'raw_response':'DO_NOT_PUBLISH'})
        store.complete_job(job, '2', 'done')
        detail = self.client.get(f'/api/agent/jobs/{job}').json
        self.assertNotIn('budget', detail.get('result',{}))
        self.assertNotIn('final_response', detail.get('result',{}))
        snapshot = self.client.get(f'/api/agent/jobs/{job}/events?snapshot=1').json
        event = next(e for e in snapshot['events'] if e['event']=='solver_progress')
        self.assertEqual('planner', event['data']['role'])
        self.assertEqual('先计算和', event['data']['solver']['progress']['steps'][0]['goal_summary'])
        self.assertNotIn('DO_NOT_PUBLISH', str(snapshot))
        stream = self.client.get(f'/api/agent/jobs/{job}/events').text
        self.assertNotIn('DO_NOT_PUBLISH', stream)
        self.assertIn('"type":"solver_progress"', stream)
        self.assertEqual(200, self.grant().status_code)
        self.assertIn('budget', self.client.get(f'/api/agent/jobs/{job}').json['result'])

    def test_answer_is_single_read_only_body_and_real_session_urls_work(self):
        headers = {'X-CSRF-Token':self.csrf,'Idempotency-Key':'51c8ba74-8eb3-46a4-9855-bc2cd516601f'}
        session = self.client.post('/api/new_chat', headers=headers).json['new_session_id']
        created = self.client.post('/api/agent/jobs', headers=headers,
            json={'session_id':session,'message':'1+1'}).json
        job = created['job_id']
        self.assertEqual(200,self.client.get('/dashboard/session/'+session).status_code)
        self.assertEqual(200,self.client.get('/api/agent/submissions/51c8ba74-8eb3-46a4-9855-bc2cd516601f').status_code)
        self.app.extensions['showcase_workspace_service'].store.complete_job(job,'2','done')
        for _ in range(2):
            answer = self.client.get(f'/api/agent/jobs/{job}/answer')
            self.assertEqual(200, answer.status_code)
            self.assertEqual('',answer.json['answer'])
            self.assertEqual('pending',answer.json['presentation_status'])
            self.assertEqual({'job_id','status','mode','answer','presentation_status','notice'},set(answer.json))
            self.assertEqual('no-store',answer.headers['Cache-Control'])
        self.assertEqual(404,self.client.get('/api/agent/jobs/foreign/answer').status_code)
        for alias in ('system','campaigns','run/old'):
            self.assertEqual(403,self.client.get('/dashboard-assets/'+alias).status_code)

    def test_reviewer_bootstrap_preserves_report_and_ownership(self):
        from tests.reviewer_support import reviewer_client
        reviewer, csrf = reviewer_client(self.app, self.client)
        headers = {'X-CSRF-Token':csrf,'Idempotency-Key':'70001278-9b9b-4cf2-905f-4f18c99e05cf'}
        session = reviewer.post('/api/new_chat',headers=headers).json['new_session_id']
        job = reviewer.post('/api/agent/jobs',headers=headers,
            json={'session_id':session,'message':'1+1'}).json['job_id']
        self.app.extensions['showcase_workspace_service'].store.complete_job(job,'2','done')
        self.assertEqual(200,reviewer.get(f'/api/agent/jobs/{job}/report').status_code)
        ordinary = self.app.test_client()
        ordinary.get('/api/check_auth')
        self.assertEqual(403,ordinary.get(f'/api/agent/jobs/{job}/report').status_code)
        service = self.app.extensions['showcase_workspace_service']
        foreign_session = service.create_session('different-owner')
        foreign, _ = service.create_job(user_id='different-owner',session_id=foreign_session,
            problem='1+1',idempotency_key='dcb224db-3708-44a1-a963-e20083744ce1')
        self.assertEqual(404,reviewer.get('/api/agent/jobs/'+foreign['job_id']+'/report').status_code)
        self.assertEqual(404,ordinary.get('/api/agent/jobs/'+foreign['job_id']+'/answer').status_code)

    def test_worker_output_is_readable_through_answer_http(self):
        import time
        self.config['SHOWCASE_WORKER_ENABLED'] = True
        self.config['SHOWCASE_JOB_DELAY_SECONDS'] = 0
        app = self.make_app()
        client = app.test_client()
        csrf = client.get('/api/check_auth').json['csrf_token']
        headers = {'X-CSRF-Token':csrf, 'Idempotency-Key':'64cdd48c-f62c-4bb0-a823-73c06663ccbf'}
        session = client.post('/api/new_chat',headers=headers).json['new_session_id']
        job = client.post('/api/agent/jobs',headers=headers,
            json={'session_id':session,'message':'1+1'}).json['job_id']
        deadline = time.monotonic() + 3
        answer = None
        while time.monotonic() < deadline:
            answer = client.get('/api/agent/jobs/'+job+'/answer')
            if answer.json['presentation_status'] == 'ready':
                break
            time.sleep(.01)
        self.assertEqual(200,answer.status_code)
        self.assertEqual('ready',answer.json['presentation_status'])
        self.assertTrue(answer.json['answer'])
        self.assertNotIn('final_response', client.get('/api/agent/jobs/'+job).json.get('result',{}))
        self.assertEqual(answer.json, client.get('/api/agent/jobs/'+job+'/answer').json)

    def test_public_grant_entry_and_ordinary_controls_reach_handlers(self):
        self.assertEqual(200, self.client.get('/dashboard/reviewer').status_code)
        for action in ('pause', 'resume'):
            response = self.client.post('/api/agent/jobs/missing/interventions/' + action,
                json={}, headers={'X-CSRF-Token': self.csrf, 'Idempotency-Key': '90a50d53-904f-4453-845a-61f15f27acc5'})
            self.assertEqual(404, response.status_code)
        self.assertEqual(403, self.client.get('/api/agent/jobs/missing/interventions').status_code)

    def test_ordinary_progress_preserves_safe_execution_mode(self):
        from showcase.public_workspace import result_view
        self.assertEqual('fake', result_view({'execution_mode': 'fake'})['execution_mode'])
