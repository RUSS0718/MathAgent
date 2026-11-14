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
        from copy import deepcopy

        from showcase.solver_harness import population_store
        from showcase.solver_harness.population_store import PopulationConflict
        command = population_store.command
        def checked_command(harness, run_id, operation, **args):
            if operation == 'intervention_complete':
                original_run = harness.get_run(run_id)
                for field in ('config_hash', 'calls', 'counters', 'population_policy'):
                    bad = deepcopy(args)
                    bad['updates'][field] = 'forbidden'
                    with self.assertRaises(PopulationConflict):
                        command(harness, run_id, operation, **bad)
                    self.assertEqual(original_run, harness.get_run(run_id))
                bad = deepcopy(args)
                bad['updates']['population']['epoch'] += 1
                with self.assertRaisesRegex(PopulationConflict, 'patch_changed'):
                    command(harness, run_id, operation, **bad)
                for boundary in ('status', 'source', 'selected_route'):
                    candidate = deepcopy(original_run['state'])
                    if boundary == 'status':
                        candidate['serial_intervention']['status'] = 'reserved'
                    elif boundary == 'source':
                        candidate['population_intervention']['source']['snapshot_hash'] = 'stale'
                    else:
                        candidate['execution_serial_route'] = 'other-route'
                    with self.assertRaises(PopulationConflict):
                        population_store._transition(harness._state_store._connection, candidate,
                            deepcopy(candidate['population']), operation, args,
                            owner_token=harness._population_owner)
                self.assertEqual(original_run, harness.get_run(run_id))
            return command(harness, run_id, operation, **args)
        self.enterContext(patch.object(population_store, 'command', checked_command))

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


class ReviewBoundaryTest(unittest.TestCase):
    def test_completion_rejects_root_identity_patch(self):
        from unittest.mock import patch

        from showcase.solver_harness.population_store import PopulationConflict, _transition
        state = {'run_id': 'r', 'state_revision': 7}
        population = {'owner': {'id': 'owner', 'epoch': 1}}
        with patch('showcase.solver_harness.product_control.controlled_patch'):
            with self.assertRaises(PopulationConflict):
                _transition(None, state, population, 'intervention_complete',
                    {'expected_revision': 7, 'updates': {'config_hash': 'other'}},
                    owner_token=population['owner'])

    def test_second_intervention_cannot_relabel_old_pair(self):
        from unittest.mock import Mock

        from showcase.solver_harness.faithful_intervention_records import FaithfulInterventionError
        from showcase.solver_harness.population_intervention import advance
        state = {'phase': 'POPULATION', 'population_intervention': {'status': 'converging'},
                 'serial_intervention': {'status': 'completed', 'pair_id': 'OLD-PAIR'}}
        harness = Mock(_intervention_enabled=True)
        with self.assertRaisesRegex(FaithfulInterventionError, 'already_used'):
            advance(harness, {'run_id': 'r', 'state_revision': 7, 'state': state}, 'problem')
        harness.commit_event.assert_not_called()

    def test_native_report_resolves_only_with_bound_parent_review(self):
        from copy import deepcopy

        from showcase.solver_harness.proof_graph_sources import importable_ledger_rows
        from showcase.solver_harness.serial_intervention import _digest
        report = {'argument': 'New argument', 'claims': [{'statement': 'new lemma'}]}
        declaration = {'category': 'Lemma', 'statement': 'new lemma', 'scope': 'problem',
                       'claim_indexes': [0], 'receipt_ids': [], 'dependencies': []}
        identity = {'run_id': 'r', 'problem_hash': 'p', 'config_hash': 'c'}
        step = {'step_id': 's'}
        reference = {**identity, 'pair_id': 'pair', 'arm': 'intervention', 'scope': 's',
                     'plan_version': 1, 'specification_version': 1, 'premises': [],
                     'dependencies': [step], 'checkpoint_hash': 'checkpoint',
                     'source_version': 'child-version', 'report_hash': _digest(report)}
        call = {**identity, 'role': 'reasoner', 'status': 'completed', 'plan_version': 1,
                'attempt_index': 0, 'request': {'step': step}, 'response': report}
        material = {'reference': reference, 'report': report, 'call': call}
        source_id = 'native-report:' + _digest(material)
        review = {**identity, 'role': 'step_verifier', 'status': 'completed',
                  'plan_version': 1, 'attempt_index': 0, 'request_revision': 20,
                  'request': {'step': step, 'report': report, 'intervention_results': [
                      {'reference': reference, 'report': report, 'evidence_grade': 'llm_reviewed'}]},
                  'response': {'verdict': 'ACCEPT', 'classified_outcomes': [declaration]}}
        state = {**identity, 'specification_version': 1, 'plan_version': 1,
                 'problem_spec': {'assumptions': []}, 'plan': {'steps': [step]},
                 'steps': {'s': {'report': report, 'verification': {'valid': True, 'verdict': 'ACCEPT'}}},
                 'calls': {'parent-review': review}, 'native_report_sources': {source_id: material}}
        row = {**declaration, 'result_id': 'parent-result', 'source': 's', 'plan_version': 1,
               'attempt_index': 0, 'specification_version': 1, 'review_call_id': 'parent-review',
               'valid': True, 'proven': True, 'evidence_level': 'llm_reviewed'}
        accepted, rejected = importable_ledger_rows(state, [row])
        self.assertEqual([], rejected)
        self.assertEqual(source_id, accepted[0][1]['report_call_id'])
        from showcase.solver_harness.population_evidence import (
            prepare_adoption,
            validate_dependencies,
        )
        from showcase.solver_harness.proof_graph import evolve_proof_graph, initial_proof_graph
        state.update(proof_graph_policy={'enabled': True}, proof_graph=initial_proof_graph(),
                     verified_results_ledger=[row], accepted_results=[])
        graph, _ = evolve_proof_graph(state, {'type': 'step_reviewed', 'verdict': 'ACCEPT', 'step_id': 's'})
        state['proof_graph'] = graph
        patch, dependencies = prepare_adoption(state, {})
        self.assertEqual(['parent-result'], patch['adopted_result_ids'])
        self.assertTrue(validate_dependencies(state, dependencies)[0])
        self.assertIn(source_id, patch['native_report_sources'])
        for mutate in ('report', 'reference', 'review'):
            bad = deepcopy(state)
            if mutate == 'report':
                bad['native_report_sources'][source_id]['report']['argument'] = 'changed'
            elif mutate == 'reference':
                bad['native_report_sources'][source_id]['reference']['source_version'] = 'changed'
            else:
                bad['calls']['parent-review']['response']['verdict'] = 'REJECT'
            self.assertEqual([], importable_ledger_rows(bad, [row])[0])
