"""D2 ordinary Job composition witness (scripted provider only)."""
import unittest

from tests import test_faithful_service_population as support
from tests.star_product_support import StarJobFixture


class PopulationInterventionTest(StarJobFixture, unittest.TestCase):
    def test_population_converges_before_native_intervention(self):
        self.run_case()

    def test_unknown_arm_blocks_and_refresh_never_redispatches(self):
        self.run_case('unknown')

    def test_cancel_in_arm_stops_dispatch(self):
        self.run_case('cancel')

    def test_source_conflict_blocks_native_dispatch(self):
        self.run_case('conflict')

    def test_revoked_permission_blocks_native_dispatch(self):
        self.run_case('permission')

    def run_case(self, fault=None):
        from unittest.mock import patch

        from showcase.solver_harness import population_intervention as composition
        advance = composition.advance
        replayed = []
        def guarded(harness, run, problem):
            if fault == 'conflict':
                with patch.object(composition, 'serial_checkpoint_view', side_effect=composition.FaithfulInterventionError('serial_checkpoint_source_changed')):
                    return advance(harness, run, problem)
            if fault == 'permission':
                with patch.object(harness, '_intervention_enabled', False):
                    return advance(harness, run, problem)
            result = advance(harness, run, problem)
            if result['state']['population_intervention']['status'] == 'completed':
                count = len(self.outbound)
                self.assertEqual(result, advance(harness, result, problem))
                self.assertEqual(count, len(self.outbound))
                replayed.append(True)
            return result
        self.enterContext(patch.object(composition, 'advance', guarded))
        original = self.open_star
        def opened(replies, **config):
            def provider(request):
                if request.get('serial_intervention_decision'):
                    return dict(decision='intervene', reason='Try construction',
                                hypothesis='Construction resolves the remaining goal', method_id=('direct' if request['plan']['steps'][0]['method_id'] == 'construction' else 'construction'))
                if fault == 'cancel' and ':pair:' not in request.get('call_id', '') and request['role'] == 'reasoner':
                    return replies[0]({**request, 'step': {**request['step'], 'step_id': request['step']['step_id'] + '-safe'}})
                if ':pair:' in request.get('call_id', '') and request['role'] == 'reasoner':
                    if fault == 'unknown':
                        from requests.exceptions import ConnectionError
                        raise ConnectionError('controlled unknown arm')
                    if fault == 'cancel':
                        response = self.client.post(f"/api/agent/jobs/{request['run_id']}/cancel", json={}, headers=self.headers())
                        self.assertEqual(200, response.status_code)
                return replies[0](request)
            original([provider] * 100, SHOWCASE_FAITHFUL_INTERVENTION_ENABLED=True, **config)
        self.open_star = opened
        job_id, final, _ = support.FaithfulPopulationJobTest.run_plain_submission(
            self, multi_step=True, modes=['intervene'], job_timeout=60, fault='cancel' if fault == 'cancel' else 'mode_crash' if fault else None)
        if fault in {'conflict', 'permission'}:
            self.assertFalse(any(':pair:' in r.get('call_id', '') for r in self.outbound))
        else:
            self.assertTrue(any(r.get('serial_intervention_decision') for r in self.outbound))
            self.assertTrue(any(':pair:' in r.get('call_id', '') for r in self.outbound))
        if not fault:
            self.assertTrue(replayed)
        if fault == 'unknown':
            projection = final['result']['solver']['serial_intervention']
            self.assertEqual('needs_review', projection['status'])
            self.assertEqual('population', projection['origin'])
        before = len(self.outbound)
        self.job(job_id)
        self.assertEqual(before, len(self.outbound))
        self.assertEqual(40, final['result']['budget']['limits']['max_model_calls'])

