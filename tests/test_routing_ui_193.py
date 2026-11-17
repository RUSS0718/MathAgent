import unittest

from tests.star_product_support import StarJobFixture, SOLVED, ACCEPT
from tests.test_adaptive_solving_job_185 import AdaptiveJobTest
from tests.test_faithful_s03_job import SPEC
from tests.test_dependency_routing_job_190 import DependencyRoutingJobTest


class RoutingUiTest(StarJobFixture, unittest.TestCase):
    open_adaptive = AdaptiveJobTest.open_adaptive

    def test_ordinary_direct_review_and_saved_answer_are_consistent(self):
        self.open_adaptive([SPEC, {**SOLVED, 'solution_candidate': '1+1=2 by integer addition.'}, ACCEPT])
        created = self.client.post('/api/agent/jobs', headers=self.headers(),
            json={'message': '1+1', 'session_id': self.session}).get_json()
        job_id = created['job_id']
        final = self.terminal(job_id)
        self.assertEqual('succeeded', final['status'])
        ordinary = self.app.test_client()
        ordinary.get('/api/check_auth')
        from showcase.output_generation import source_job
        from showcase.presentation import presentation_snapshot, build_presentation
        service = self.app.extensions['showcase_workspace_service']
        snapshot = presentation_snapshot(source_job(service, 'local-user', job_id))
        # Reproduce a pre-fix cached original: no claim refs, partial completion.
        cached = build_presentation(snapshot, 'solve', paragraphs=[
            {'kind': 'mathematical', 'text': snapshot['answer'], 'claim_refs': []}])
        import json
        cached['rule'] = snapshot['rule']
        # Historical-storage fixture in this test's temporary database only.
        with service.store._lock, service.store._connection:
            service.store._connection.execute(
                'UPDATE presentation_artifacts SET artifact_json=? WHERE job_id=?',
                (json.dumps(cached), job_id))
        for _ in range(2):
            answer = ordinary.get(f'/api/agent/jobs/{job_id}/answer').get_json()
            self.assertEqual('ready', answer['presentation_status'], answer)
            self.assertIn('整题模型审查', answer['notice'])
            self.assertNotIn('部分结果', answer['notice'])
            self.assertNotIn('当前答复未验证', answer['notice'])
        self.assertEqual(cached, service.get_presentation(user_id='local-user', job_id=job_id,
            mode='solve', source_fingerprint=snapshot['fingerprint']))
        self.assertEqual(0, snapshot['scope']['covered'])
        self.assertTrue(snapshot['scope']['unresolved'])
        self.assertEqual(3, len(self.outbound))

    def test_ordinary_event_routes_are_safe_and_read_only(self):
        DependencyRoutingJobTest.test_dependencies_plan_before_solving_and_execute_ordered_work_units(self)
        job_id = self.created_job
        ordinary = self.app.test_client()
        ordinary.get('/api/check_auth')
        summaries = []
        cursor = 0
        while True:
            page = ordinary.get(f'/api/agent/jobs/{job_id}/events?snapshot=1&limit=100&last_event_id={cursor}').get_json()
            summaries.extend(event['data'].get('routing_summary') for event in page['events'])
            self.assertNotIn('PRIVATE', str(page))
            if not page['has_more']:
                break
            cursor = page['next_cursor']
        self.assertIn('题目中的目标有先后依赖，先制定分步方案。', summaries)
        self.assertEqual(8, len(self.outbound))

    def create_job(self):
        self.created_job = super().create_job()
        return self.created_job

    def test_rewritten_answer_does_not_inherit_original_review(self):
        from tests.star_product_support import RawProviderContent
        self.open_adaptive([SPEC, SOLVED, ACCEPT, RawProviderContent('改写后的数学答复：2。')])
        self.app.config['SHOWCASE_PRESENTATION_ENABLED'] = True
        created = self.client.post('/api/agent/jobs', headers=self.headers(),
            json={'message': '1+1', 'session_id': self.session, 'presentation_mode': 'teach'}).get_json()
        job_id = created['job_id']
        self.terminal(job_id)
        ordinary = self.app.test_client()
        ordinary.get('/api/check_auth')
        answer = ordinary.get(f'/api/agent/jobs/{job_id}/answer').get_json()
        self.assertIn('当前答复未验证', answer['notice'])
        self.assertNotIn('已完成并经整题模型审查', answer['notice'])
        self.assertEqual('改写后的数学答复：2。', answer['answer'])
        ordinary.get(f'/api/agent/jobs/{job_id}/answer')
        self.assertEqual(4, len(self.outbound))

class PresentationSourceTest(unittest.TestCase):
    def test_wrong_run_review_cannot_support_current_answer(self):
        from tests.test_faithful_f6_presentation import evidence_job
        from showcase.presentation import presentation_snapshot, build_presentation
        job = evidence_job()
        job['result']['verification']['history'][0]['source'] = {'run_id': 'another-run'}
        artifact = build_presentation(presentation_snapshot(job), 'solve')
        self.assertEqual('not_verified', artifact['delivery']['grade'])
