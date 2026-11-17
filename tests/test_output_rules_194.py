import unittest

from showcase.presentation_api import get_final_answer


class OutputRulesTest(unittest.TestCase):
    def test_default_job_freezes_rule_and_worker_saves_answer(self):
        import tempfile

        from showcase.flask_app import create_app
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        app = create_app({'TESTING': True, 'SHOWCASE_DATA_DIR': directory.name,
                          'SHOWCASE_WORKER_ENABLED': False, 'SHOWCASE_JOB_DELAY_SECONDS': 0})
        for key in ('showcase_workspace_service', 'showcase_run_service', 'loopback_store'):
            self.addCleanup(app.extensions[key].close)
        service = app.extensions['showcase_workspace_service']
        session = service.create_session('owner')
        job, _ = service.create_job(user_id='owner', session_id=session, problem='1+1', idempotency_key='147142a4-1cbd-455b-9fe6-553045472692')
        service._execute(job['job_id'])
        answer = get_final_answer(service, 'owner', job['job_id'])
        self.assertEqual('ready', answer['presentation_status'])
        self.assertEqual('solve', answer['mode'])
        self.assertIn('Fake Agent', answer['answer'])
        result = service.get_job(job['job_id'], 'owner')['result']
        self.assertEqual(64, len(result['presentation_rule']['sha256']))

    def test_new_output_post_cannot_generate_template_before_worker(self):
        import tempfile

        from showcase.flask_app import create_app
        with tempfile.TemporaryDirectory() as directory:
            app = create_app({'TESTING': True, 'SHOWCASE_DATA_DIR': directory,
                              'SHOWCASE_PRESENTATION_ENABLED': True, 'SHOWCASE_WORKER_ENABLED': False})
            try:
                from tests.reviewer_support import reviewer_client
                client, _ = reviewer_client(app)
                headers = {'X-CSRF-Token': client.get('/api/check_auth').get_json()['csrf_token'],
                           'Idempotency-Key': '147142a4-1cbd-455b-9fe6-553045472693'}
                session = client.post('/api/new_chat', headers=headers).get_json()['new_session_id']
                created = client.post('/api/agent/jobs', json={'message': '1+1', 'session_id': session,
                                      'presentation_mode': 'teach'}, headers=headers).get_json()
                service = app.extensions['showcase_workspace_service']
                service.store.start_job(created['job_id'])
                service.store.complete_job(created['job_id'], '2', 'known answer')
                response = client.post('/api/agent/jobs/' + created['job_id'] + '/teach', json={}, headers=headers)
                self.assertEqual(409, response.status_code)
                self.assertEqual([], service.list_presentations(user_id='local-user', job_id=created['job_id'], mode='teach'))
            finally:
                for key in ('showcase_workspace_service', 'showcase_run_service', 'loopback_store'):
                    app.extensions[key].close()

class TerminalOutputContractTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        from showcase.flask_app import create_app
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.app = create_app({'TESTING': True, 'SHOWCASE_DATA_DIR': self.directory.name,
                              'SHOWCASE_PRESENTATION_ENABLED': True, 'SHOWCASE_WORKER_ENABLED': False})
        for key in ('showcase_workspace_service', 'showcase_run_service', 'loopback_store'):
            self.addCleanup(self.app.extensions[key].close)
        self.service = self.app.extensions['showcase_workspace_service']
        from tests.reviewer_support import reviewer_client
        self.client, _ = reviewer_client(self.app)
        self.headers = {'X-CSRF-Token': self.client.get('/api/check_auth').get_json()['csrf_token']}
        self.session = self.client.post('/api/new_chat', headers=self.headers).get_json()['new_session_id']

    def job(self, mode):
        import uuid
        response = self.client.post('/api/agent/jobs', json={'message': '计算 1+1；仅假设通常整数加法',
            'session_id': self.session, 'presentation_mode': mode},
            headers={**self.headers, 'Idempotency-Key': str(uuid.uuid4())})
        self.assertEqual(202, response.status_code, response.get_json())
        return response.get_json()['job_id']

    def model(self, text='先理解加法，再得出 2。', reason='stop', mutate=None):
        import json
        import os
        from types import SimpleNamespace
        from unittest.mock import patch

        from llm_client import InternChatClient
        from showcase.adapters import InternModelAdapter
        self.enterContext(patch.dict(os.environ, {'INTERN_API_KEY': 'controlled-offline'}))
        self.service.pipeline = SimpleNamespace(model=InternModelAdapter(InternChatClient(retry=3)))
        self.requests = []
        def respond(*args, **kwargs):
            self.requests.append(json.loads(kwargs['data']))
            if mutate:
                mutate()
            if isinstance(text, BaseException):
                raise text
            class Response:
                status_code = 200
                def close(self): pass
                def raise_for_status(self): pass
                def iter_content(self, chunk_size=1):
                    yield json.dumps({'choices': [{'finish_reason': reason, 'message': {'content': text}}],
                        'model': 'intern-s2', 'usage': {'prompt_tokens': 7, 'completion_tokens': 3,
                                                     'total_tokens': 10}}).encode()
            return Response()
        return self.enterContext(patch('llm_client.requests.post', side_effect=respond))

    def complete(self, job_id):
        self.service.store.start_job(job_id)
        self.service.store.complete_job(job_id, '1+1=2', 'known partial answer')

    def generate(self, job_id):
        from showcase.output_generation import generate_terminal
        generate_terminal(self.service, job_id)

    def answer(self, job_id):
        return get_final_answer(self.service, 'local-user', job_id)

    def test_teach_model_once_and_reads_never_dispatch(self):
        post = self.model()
        job_id = self.job('teach')
        self.complete(job_id)
        self.assertEqual('pending', self.answer(job_id)['presentation_status'])
        self.generate(job_id)
        self.generate(job_id)
        for _ in range(3):
            self.assertEqual('ready', self.answer(job_id)['presentation_status'])
            response = self.client.get(f'/api/agent/jobs/{job_id}/outputs/teach')
            self.assertEqual(200, response.status_code)
        artifact = response.get_json()['presentation']
        self.assertEqual(1, post.call_count)
        self.assertEqual(4096, self.requests[0]['max_tokens'])
        self.assertNotIn('tools', self.requests[0])
        self.assertIn('通常整数加法', self.requests[0]['messages'][-1]['content'])
        self.assertEqual(10, artifact['output_request']['usage']['total_tokens'])
        self.assertEqual('not_verified', artifact['paragraphs'][0]['grade'])
        self.assertEqual('not_verified', artifact['delivery']['grade'])
        self.assertEqual(3, self.service.pipeline.model._client.retry)

    def test_report_model_context_contains_problem_scope_and_evidence(self):
        self.model('问题：加法。假设：整数。结论：2。验证范围：未验证。未完成目标：无独立证明。')
        job_id = self.job('report')
        self.complete(job_id)
        self.generate(job_id)
        self.assertEqual('ready', self.answer(job_id)['presentation_status'])
        self.assertIn('evidence_summary', self.requests[0]['messages'][-1]['content'])
        self.assertIn('scope', self.requests[0]['messages'][-1]['content'])

    def test_truncated_output_is_durable_failure_without_retry(self):
        post = self.model('未完整', reason='length')
        job_id = self.job('teach')
        self.complete(job_id)
        self.generate(job_id)
        self.generate(job_id)
        self.assertEqual(1, post.call_count)
        self.assertEqual('failed', self.answer(job_id)['presentation_status'])
        self.assertEqual('1+1=2', self.answer(job_id)['answer'])

    def test_timeout_unknown_not_resent_after_restart(self):
        import requests

        from showcase.output_generation import initialize_generation
        post = self.model(requests.ReadTimeout('controlled timeout'))
        job_id = self.job('report')
        self.complete(job_id)
        self.generate(job_id)
        initialize_generation(self.service.store)
        self.generate(job_id)
        self.assertEqual(1, post.call_count)
        self.assertEqual('failed', self.answer(job_id)['presentation_status'])

    def test_source_change_during_generation_returns_current_fallback(self):
        job_id = self.job('teach')
        self.complete(job_id)
        def change():
            self.service.store.append_event(job_id, {'type': 'tool_call_result', 'message': 'new evidence'})
        self.model(mutate=change)
        self.generate(job_id)
        self.assertEqual('stale', self.answer(job_id)['presentation_status'])
        self.assertEqual('1+1=2', self.answer(job_id)['answer'])
        self.assertEqual([], self.service.list_presentations(user_id='local-user',job_id=job_id,mode='teach'))

    def test_missing_model_fails_and_legacy_never_generates(self):
        import json
        job_id = self.job('teach')
        self.service._execute(job_id)
        self.assertEqual('failed', self.answer(job_id)['presentation_status'])
        store = self.service.store
        with store._lock:
            result = store.job_identity(job_id)
            result.pop('presentation_rule')
            store._connection.execute('UPDATE workspace_jobs SET result_json=? WHERE job_id=?',
                                      (json.dumps(result), job_id))
            store._connection.commit()
        self.generate(job_id)
        self.assertEqual('legacy', self.answer(job_id)['presentation_status'])

    def test_existing_generating_claim_is_unknown_on_restart_and_never_resent(self):
        from showcase.output_generation import initialize_generation, source_job
        from showcase.presentation import presentation_snapshot
        post = self.model()
        job_id = self.job('report')
        self.complete(job_id)
        source = presentation_snapshot(source_job(self.service, 'local-user', job_id))['fingerprint']
        with self.service.store._lock:
            self.service.store._connection.execute('INSERT INTO output_generations VALUES(?,?,?,?,?)',
                (job_id, source, 'generating', 'interrupted-request', '{}'))
            self.service.store._connection.commit()
        initialize_generation(self.service.store)
        self.generate(job_id)
        self.assertEqual('failed', self.answer(job_id)['presentation_status'])
        self.assertEqual(0, post.call_count)

    def test_failed_partial_answer_can_be_formatted_without_claim_upgrade(self):
        self.model('即使模型说已证明，也仍未验证。')
        job_id = self.job('report')
        self.complete(job_id)
        with self.service.store._lock:
            self.service.store._connection.execute("UPDATE workspace_jobs SET status='failed' WHERE job_id=?", (job_id,))
            self.service.store._connection.commit()
        self.generate(job_id)
        self.assertEqual('ready', self.answer(job_id)['presentation_status'])
        artifact = self.service.list_presentations(user_id='local-user', job_id=job_id, mode='report')[0]
        self.assertEqual('partial', artifact['completion'])
        self.assertEqual('not_verified', artifact['delivery']['grade'])
        self.assertEqual([], artifact['delivery']['verified_claims'])

    def test_rule_change_invalidates_saved_output_without_dispatch(self):
        import json
        post = self.model()
        job_id = self.job('teach')
        self.complete(job_id)
        self.generate(job_id)
        with self.service.store._lock:
            result = self.service.store.job_identity(job_id)
            result['presentation_rule']['sha256'] = 'new-rule-content-hash'
            self.service.store._connection.execute('UPDATE workspace_jobs SET result_json=? WHERE job_id=?',
                (json.dumps(result), job_id))
            self.service.store._connection.commit()
        self.generate(job_id)
        self.assertEqual('stale', self.answer(job_id)['presentation_status'])
        self.assertEqual(1, post.call_count)

    def test_canceled_known_answer_and_cross_owner_reads(self):
        from showcase.workspace import WorkspaceError
        post = self.model()
        job_id = self.job('teach')
        self.complete(job_id)
        with self.service.store._lock:
            self.service.store._connection.execute("UPDATE workspace_jobs SET status='canceled' WHERE job_id=?", (job_id,))
            self.service.store._connection.commit()
        self.generate(job_id)
        self.assertEqual('failed', self.answer(job_id)['presentation_status'])
        self.assertEqual('1+1=2', self.answer(job_id)['answer'])
        self.assertEqual(0, post.call_count)
        with self.assertRaises(WorkspaceError):
            get_final_answer(self.service, 'another-user', job_id)

    def test_partial_answer_notice_preserves_scope_without_duplicate_body(self):
        job_id = self.job('solve')
        self.complete(job_id)
        self.generate(job_id)
        answer = self.answer(job_id)
        self.assertEqual('1+1=2', answer['answer'])
        self.assertIn('未完成', answer['notice'])
        self.assertIn('未验证', answer['notice'])

    def test_fallback_notices_use_current_scope_through_ordinary_answer_http(self):
        import json
        from unittest.mock import patch

        from showcase.presentation import presentation_snapshot

        ordinary = self.app.test_client()
        ordinary.get('/api/check_auth')
        with patch('llm_client.requests.post', side_effect=AssertionError('GET must not dispatch')) as post:
            for state, expected, complete in (
                ('failed', 'failed', False), ('unknown', 'failed', False),
                ('stale', 'stale', False), ('source_changed', 'stale', False),
                ('ready', 'unavailable', False), ('legacy', 'legacy', False),
                ('failed', 'failed', True),
            ):
                with self.subTest(state=state, complete=complete):
                    job_id = self.job('teach')
                    self.complete(job_id)
                    store = self.service.store
                    result = store.job_identity(job_id)
                    result['solver'] = {
                        'semantics': {'whole_review': 'accepted' if complete else 'not_reviewed',
                                      'binding': 'same_artifact'},
                        'progress': {'root_obligations': {
                            'covered': 2 if complete else 1, 'total': 2,
                            'items': [{'ordinal': 1, 'status': 'satisfied'},
                                      {'ordinal': 2, 'status': 'satisfied' if complete else 'unresolved'}],
                        }},
                    }
                    if state == 'legacy':
                        result.pop('presentation_rule')
                    if complete:
                        from showcase.final_evidence import bind_verification
                        result['verification'] = bind_verification('1+1=2', {
                            'status': 'unknown', 'scope': 'whole_solution_llm_review',
                            'findings': ['llm_whole_review_accept'],
                        })
                    with store._lock:
                        store._connection.execute('UPDATE workspace_jobs SET result_json=? WHERE job_id=?',
                                                  (json.dumps(result), job_id))
                        snapshot = presentation_snapshot(store.get_job(job_id, 'local-user'))
                        source = 'older-source' if state == 'source_changed' else snapshot['fingerprint']
                        store._connection.execute('INSERT INTO output_generations VALUES(?,?,?,?,?)',
                            (job_id, source, 'ready' if state == 'source_changed' else state, 'saved-request', '{}'))
                        store._connection.commit()
                    response = ordinary.get(f'/api/agent/jobs/{job_id}/answer')
                    self.assertEqual(200, response.status_code)
                    self.assertEqual(expected, response.json['presentation_status'])
                    self.assertEqual('1+1=2', response.json['answer'])
                    self.assertNotIn('1+1=2', response.json['notice'])
                    if complete:
                        self.assertNotIn('未完成', response.json['notice'])
                        self.assertNotIn('未验证', response.json['notice'])
                    else:
                        self.assertIn('已覆盖 1/2', response.json['notice'])
                        self.assertEqual(1, response.json['notice'].count('未完成目标'))
                        self.assertEqual(1, response.json['notice'].count('未验证'))
            self.assertEqual(0, post.call_count)

    def test_restart_orphaned_terminal_answer_falls_back_without_dispatch(self):
        from showcase.output_generation import initialize_generation
        job_id = self.job('teach')
        self.complete(job_id)
        post = self.model()
        initialize_generation(self.service.store)
        for _ in range(2):
            answer = self.client.get(f'/api/agent/jobs/{job_id}/answer').get_json()
            self.assertEqual('failed', answer['presentation_status'])
            self.assertEqual('1+1=2', answer['answer'])
        self.generate(job_id)
        self.assertEqual(0, post.call_count)

    def test_empty_source_is_unavailable_through_public_answer_http(self):
        job_id = self.job('solve')
        self.service.store.start_job(job_id)
        self.service.store.complete_job(job_id, '', 'no answer')
        self.generate(job_id)
        for state in ('failed', 'unknown', 'stale', 'ready'):
            with self.subTest(state=state):
                with self.service.store._lock:
                    self.service.store._connection.execute('UPDATE output_generations SET status=? WHERE job_id=?',
                                                          (state, job_id))
                    self.service.store._connection.commit()
                response = self.client.get(f'/api/agent/jobs/{job_id}/answer')
                self.assertEqual(200, response.status_code)
                self.assertEqual('unavailable', response.json['presentation_status'])
                self.assertEqual('', response.json['answer'])
                self.assertNotIn('原答案', response.json['notice'])
                self.assertNotIn('未完成', response.json['notice'])
