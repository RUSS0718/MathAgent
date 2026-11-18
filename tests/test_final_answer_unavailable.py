"""Final-answer availability is independent of expression artifact readiness."""

import json
import tempfile
import unittest
from unittest.mock import patch

from showcase.flask_app import create_app
from showcase.output_generation import generate_terminal
from showcase.presentation import build_presentation, presentation_snapshot
from showcase.presentation_api import get_final_answer
from showcase.solver_harness.result import export_result


class FinalAnswerUnavailableTest(unittest.TestCase):
    """Exercise ordinary answer GETs against an isolated, workerless workspace."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.app = create_app({'TESTING': True, 'SHOWCASE_DATA_DIR': directory.name,
                               'SHOWCASE_WORKER_ENABLED': False})
        for key in ('showcase_workspace_service', 'showcase_run_service', 'loopback_store'):
            self.addCleanup(self.app.extensions[key].close)
        self.service = self.app.extensions['showcase_workspace_service']
        self.client = self.app.test_client()
        self.client.get('/api/check_auth')
        self.session = self.service.create_session('local-user')

    def saved_job(self, answer, *, status='failed', mode='solve', state='ready', solver=None):
        """Persist a terminal result and its independently saved output state."""
        import uuid

        job, _ = self.service.create_job(
            user_id='local-user', session_id=self.session, problem='求两个目标',
            idempotency_key=str(uuid.uuid4()), presentation_mode=mode)
        job_id = job['job_id']
        store = self.service.store
        store.start_job(job_id)
        store.complete_job(job_id, answer, 'controlled result')
        result = store.job_identity(job_id)
        if solver is not None:
            result['solver'] = solver
        if state == 'legacy':
            result.pop('presentation_rule')
        with store._lock:
            store._connection.execute(
                'UPDATE workspace_jobs SET status=?,result_json=? WHERE job_id=?',
                (status, json.dumps(result), job_id))
            store._connection.commit()
        if state == 'ready' and mode == 'solve':
            generate_terminal(self.service, job_id)
        elif state != 'legacy':
            snapshot = presentation_snapshot(store.get_job(job_id, 'local-user'))
            if state == 'ready':
                artifact = build_presentation(snapshot, mode, paragraphs=[
                    {'text': '整理后的表达，不能凭此认定已有答案。', 'kind': 'mathematical'}])
                artifact['rule'] = snapshot['rule']
                self.service.save_presentation(user_id='local-user', job_id=job_id, artifact=artifact)
            with store._lock:
                store._connection.execute('INSERT INTO output_generations VALUES(?,?,?,?,?)',
                                          (job_id, snapshot['fingerprint'], state, 'saved-output', '{}'))
                store._connection.commit()
        return job_id

    def assert_unavailable(self, job_id, status='failed'):
        response = self.client.get(f'/api/agent/jobs/{job_id}/answer')
        self.assertEqual(200, response.status_code)
        self.assertEqual('no-store', response.headers['Cache-Control'])
        self.assertEqual(status, response.json['status'])
        self.assertEqual('unavailable', response.json['presentation_status'])
        self.assertEqual('', response.json['answer'])
        self.assertIn('没有可用', response.json['notice'])
        return response.json

    def test_internal_fallback_with_ready_artifact_is_unavailable(self):
        fallback = export_result({})['final_response']
        job_id = self.saved_job(fallback, solver={'candidate_history': [], 'best_effort': None})
        artifact = self.service.list_presentations(user_id='local-user', job_id=job_id, mode='solve')[0]
        self.assertEqual('ready', artifact['status'])
        self.assert_unavailable(job_id)
        self.assertEqual(fallback, self.service.store.get_job(job_id, 'local-user')['result']['final_response'])

    def test_fallback_is_unavailable_across_output_states_and_modes(self):
        for mode in ('solve', 'teach', 'report'):
            for state in ('ready', 'failed', 'unknown', 'stale', 'generating', 'legacy'):
                with self.subTest(mode=mode, state=state):
                    self.assert_unavailable(self.saved_job(export_result({})['final_response'],
                                                           mode=mode, state=state))

    def test_empty_source_cannot_become_an_answer_via_ready_expression(self):
        for answer in ('', '   '):
            with self.subTest(answer=answer):
                self.assert_unavailable(self.saved_job(answer, mode='teach'))

    def test_terminal_job_status_is_preserved(self):
        for status in ('failed', 'canceled', 'succeeded'):
            with self.subTest(status=status):
                self.assert_unavailable(self.saved_job(export_result({})['final_response'], status=status), status)

    def test_failed_real_partial_answer_is_preserved(self):
        answer = '已得第一个目标 x=2，第二个目标尚未完成。'
        solver = {'progress': {'root_obligations': {'covered': 1, 'total': 2}},
                  'candidate_history': [{'candidate_id': 'partial-1', 'version': 1,
                                         'answer_text': answer, 'answer_completeness': 'partial',
                                         'selection_eligible': True}],
                  'best_effort': {'selected_candidate_id': 'partial-1', 'selected_candidate_version': 1},
                  'semantics': {'whole_review': 'accepted', 'binding': 'same_artifact'}}
        job_id = self.saved_job(answer, solver=solver)
        response = self.client.get(f'/api/agent/jobs/{job_id}/answer').json
        self.assertEqual('failed', response['status'])
        self.assertEqual('ready', response['presentation_status'])
        self.assertEqual(answer, response['answer'])
        self.assertIn('已覆盖 1/2', response['notice'])
        self.assertIn('未验证', response['notice'])
        self.assertNotIn('已完成并经整题模型审查', response['notice'])

    def test_running_empty_source_remains_pending(self):
        job_id = self.saved_job('', status='running', state='generating')
        result = get_final_answer(self.service, 'local-user', job_id)
        self.assertEqual('running', result['status'])
        self.assertEqual('pending', result['presentation_status'])
        self.assertEqual('', result['answer'])

    def test_fallback_failure_keeps_real_partial_answer(self):
        for state in ('failed', 'unknown', 'stale', 'legacy'):
            with self.subTest(state=state):
                job_id = self.saved_job('第一个目标 x=2。', state=state)
                result = get_final_answer(self.service, 'local-user', job_id)
                self.assertEqual('第一个目标 x=2。', result['answer'])
                self.assertNotEqual('unavailable', result['presentation_status'])

    def test_read_repeats_do_not_write_generate_or_dispatch(self):
        job_id = self.saved_job(export_result({})['final_response'])
        connection = self.service.store._connection
        before = connection.total_changes
        with patch('showcase.output_generation.generate_terminal', side_effect=AssertionError('GET generation')), \
             patch('llm_client.requests.post', side_effect=AssertionError('GET model call')), \
             patch.object(self.service, 'save_presentation', side_effect=AssertionError('GET save')):
            first = self.assert_unavailable(job_id)
            self.assertEqual(first, self.assert_unavailable(job_id))
        self.assertEqual(before, connection.total_changes)
