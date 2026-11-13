"""Public native result adoption preserves source grade and parent authority."""
import unittest

from tests import test_faithful_s10_native_checkpoint as native_support


class SerialAdoptionTest(unittest.TestCase):
    setUp = native_support.NativeCheckpointTest.setUp
    reserve = native_support.NativeCheckpointTest.reserve
    def test_native_children_are_independently_reviewed_and_parent_is_unchanged(self):
        native_support.NativeCheckpointTest.test_native_children_are_independently_reviewed_and_parent_is_unchanged(self)
        from showcase.solver_harness.serial_intervention import result_reference, adopt_result
        from showcase.solver_harness import SolverHarness
        with SolverHarness(store=self.store, config={'max_model_calls': 20, 'features': {'problem_spec': True, 'progress_scheduling': True, 'serial_routes': True, 'proof_graph': True, 'stream_recovery': True, 'persistent_sessions': True, 'final_generation': True, 'final_solution_review': True}}) as harness:
            parent = harness.get_run('native-parent')
            reference = result_reference(self.engine, 'native-pair', 'intervention')
            before = parent['state'].get('verified_results_ledger', [])
            adopted = adopt_result(harness, parent, self.engine, reference)
            self.assertEqual('adopted', adopted['state']['serial_intervention']['adoptions'][-1]['status'])
            self.assertEqual(before, adopted['state'].get('verified_results_ledger', []))
            self.assertEqual('llm_reviewed', adopted['state']['serial_intervention']['adoptions'][-1]['evidence_grade'])
            from showcase.solver_harness.serial_intervention import public_projection
            public = public_projection(adopted['state']['serial_intervention'])
            self.assertEqual({'pair_id', 'arm', 'source_version', 'scope'}, set(public['adoptions'][-1]['reference']))
            invalid = dict(reference, result_id='missing-proof')
            rejected_proof = adopt_result(harness, adopted, self.engine, invalid)
            self.assertEqual('source_proof_not_applicable', rejected_proof['state']['serial_intervention']['adoptions'][-1]['reason'])
            adopted = rejected_proof
            stale = dict(reference, source_version='stale')
            rejected = adopt_result(harness, adopted, self.engine, stale)
            self.assertEqual('source_version_changed', rejected['state']['serial_intervention']['adoptions'][-1]['reason'])


from tests.star_product_support import StarJobFixture


class SerialPublicJobTest(StarJobFixture, unittest.TestCase):
    def test_ordinary_obstacle_runs_native_pair_and_continues_with_whole_review(self):
        self.run_intervention()

    def test_unknown_arm_is_not_resent_by_refresh(self):
        self.run_intervention('unknown')

    def test_cancel_in_first_arm_stops_all_further_dispatch(self):
        self.run_intervention('cancel')

    def run_intervention(self, fault=None):
        from copy import deepcopy
        from tests.test_faithful_service_population import FaithfulPopulationJobTest
        original_open = self.open_star
        def opened(replies, **config):
            proposal_seen = False
            def provider(request):
                nonlocal proposal_seen
                if request.get('serial_intervention_decision'):
                    proposal_seen = True
                    return {'decision': 'intervene', 'reason': 'Direct approach stalled',
                            'hypothesis': 'Construction establishes the missing value', 'method_id': 'construction'}
                if request.get('execution_mode_decision'):
                    return {'mode': 'keep', 'reason': 'Continue serial'}
                if request['role'] == 'meta':
                    return {'decision': 'CONTINUE', 'reason_summary': 'Use the experiment result',
                            'plan_summary': '', 'forbidden_directions': [], 'reusable_results': [], 'trace_back_to': None}
                if request['role'] == 'step_verifier' and not proposal_seen:
                    return {'goal_gate': 'NO', 'logic_gate': 'FAIL', 'verdict': 'CHALLENGE',
                            'objection': 'The direct argument does not establish the value', 'obligation_evidence': []}
                if proposal_seen and request['role'] == 'reasoner' and fault:
                    if fault == 'unknown':
                        from requests.exceptions import ConnectionError
                        raise ConnectionError('unknown experiment arm')
                    canceled = self.client.post(f"/api/agent/jobs/{request['run_id']}/cancel",
                                                json={}, headers=self.headers())
                    self.assertEqual(200, canceled.status_code)
                reply = deepcopy(replies[0](request))
                if proposal_seen and request['role'] == 'reasoner':
                    reply['argument'] = 'Construction proves 1+1=2'
                if request['role'] == 'planner':
                    reply['alternative_plans'] = []
                return reply
            original_open([provider] * 40, **config)
        self.open_star = opened
        job_id, final, _ = FaithfulPopulationJobTest.run_plain_submission(self, selection_mode='serial', fault='cancel' if fault == 'cancel' else 'mode_unknown' if fault else None)
        solver = final['result']['solver']
        if fault:
            arms = [r['call_id'] for r in self.outbound if r['role'] == 'reasoner' and ':pair:' in r['call_id']]
            self.assertEqual(1 if fault == 'cancel' else 2, len(arms))
            self.assertEqual(len(arms), len(set(arms)))
            before = len(self.outbound)
            self.job(job_id)
            self.report(job_id)
            self.assertEqual(before, len(self.outbound))
            return
        self.assertEqual('completed', solver['serial_intervention']['status'], solver)
        self.assertEqual('adopted', solver['serial_intervention']['adoptions'][0]['status'])
        self.assertEqual(solver['serial_intervention'], solver['progress']['serial_intervention'])
        self.assertGreaterEqual(sum(r['role'] == 'step_verifier' for r in self.outbound), 5)
        self.assertTrue(any(r['role'] == 'whole_solution_verifier' for r in self.outbound))
        before = len(self.outbound)
        self.job(job_id)
        self.report(job_id)
        self.assertEqual(before, len(self.outbound))

