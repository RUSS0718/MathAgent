"""#179: current consent fences persisted advisory at request preparation."""
import json
import unittest
from copy import deepcopy
from types import SimpleNamespace

from showcase.solver_harness.harness import SolverHarness
from tests import test_faithful_s10_memory_injection as fixtures
from tests.star_product_support import StarJobFixture


class Service179MemoryTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.FaithfulS10MemoryInjectionTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.fixture.add_entry('hint', payload={
            'observation': {'outcome': 'success', 'applicability': {'domain': 'Algebra'},
                            'versions': {}, 'cost': {}, 'content': {'hint': 'factor'}},
            'provenance': {'source_run_id': 'current-run'},
        })
        self.memory = self.fixture.load({'domain': 'Algebra'})
        self.assertEqual(1, len(self.memory['observations']))
        self.run = {'run_id': 'current-run', 'state_revision': 1, 'state': {
            'population_memory_advisory': self.memory,
            'problem_spec': {'domain': 'Algebra', 'original_problem': 'factor x',
                             'specification_version': 1},
        }}
        self.harness = SimpleNamespace(
            _population_memory_enabled=True,
            _config={'features': {'persistent_sessions': True}}, _tool_port=None,
            _state_store=SimpleNamespace(_connection=self.fixture.db),
            get_run=lambda _: deepcopy(self.run),
        )

    def prepare(self):
        return SolverHarness.prepare_request(self.harness, self.run, {
            'role': 'reasoner', 'population_memory_advisory': self.memory,
            'session_history': [{'request': {'population_memory_advisory': self.memory},
                                 'response': {'argument': 'historical exchange'}}],
        })

    def test_disabled_consent_filters_current_and_history_after_restore(self):
        self.assertIn('hint', json.dumps(self.prepare()))
        self.fixture.db.execute('UPDATE faithful_memory_injection_controls SET enabled=0')
        # The same persisted state is loaded afresh, as on restart.
        self.run = json.loads(json.dumps(self.run))
        prepared = self.prepare()
        self.assertNotIn('population-memory-injection-v1', json.dumps(prepared))
        self.assertNotIn('historical exchange', json.dumps(prepared))
        self.assertEqual(1, len(self.run['state']['population_memory_advisory']['observations']))

    def test_revoked_record_filters_persisted_copy(self):
        self.fixture.db.execute("UPDATE faithful_memory_entries SET state='cleared'")
        self.assertNotIn('population-memory-injection-v1', json.dumps(self.prepare()))

    def test_modified_persisted_content_is_replaced_from_source(self):
        self.run['state']['population_memory_advisory']['observations'][0]['content'] = {'hint': 'forged'}
        prepared = self.prepare()
        self.assertNotIn('forged', json.dumps(prepared))
        self.assertIn('factor', json.dumps(prepared))

    def test_intake_spec_loads_without_initial_advisory(self):
        self.run['state'].pop('population_memory_advisory')
        prepared = SolverHarness.prepare_request(self.harness, self.run, {'role': 'reasoner'})
        self.assertEqual(['hint'], [item['record_id'] for item in
                                   prepared['population_memory_advisory']['observations']])

    def test_source_session_opt_out_invalidates_imported_ancestor(self):
        from tests import test_faithful_s10_memory_import_chain as chains
        fixture = chains.MemoryImportChainTest()
        fixture.setUp()
        try:
            self.assertEqual(1, len(fixture.load()))
            fixture.db.execute("INSERT INTO faithful_memory_injection_controls "
                               "VALUES ('owner','a','population','a',0,'now')")
            self.assertEqual([], fixture.load())
        finally:
            fixture.doCleanups()

    def test_memory_decisions_are_optional_bounded_and_source_scoped_schema(self):
        from showcase.solver_harness.intern_schemas import response_schema
        prepared = self.prepare()
        schema = response_schema(prepared)
        decisions = schema['properties']['memory_decisions']
        self.assertNotIn('memory_decisions', schema['required'])
        self.assertEqual(['hint'], decisions['items']['properties']['record_id']['enum'])
        self.assertEqual(['adopt', 'reject'], decisions['items']['properties']['decision']['enum'])
        self.assertEqual(500, decisions['items']['properties']['reason']['maxLength'])
        from showcase.tool_schemas import schema_error
        valid = {'record_id': 'hint', 'decision': 'adopt', 'reason': 'Use as a hint only.'}
        self.assertIsNone(schema_error([valid], decisions))
        for invalid in ({**valid, 'record_id': 'foreign'}, {**valid, 'reason': 'x' * 501},
                        {**valid, 'decision': 'verified'}, {**valid, 'reason': ''}):
            self.assertIsNotNone(schema_error([invalid], decisions))



class Service179PublicMemoryTest(StarJobFixture, unittest.TestCase):
    def test_public_opt_out_then_explicit_resume_filters_history_and_keeps_audit(self):
        import os
        import sqlite3
        import uuid
        from contextlib import closing
        from unittest.mock import patch

        import requests

        from showcase.run_budget import RunBudgetLimits
        from tests.test_faithful_s03_job import CAPACITY_POLICY, ENDPOINT, PROBLEM, REPLIES, SPEC

        def choose_memory(_context):
            record_id = self.client.get(url).get_json()['observations'][0]['record_id']
            return {**deepcopy(REPLIES[0]), 'memory_decisions': [{
                'record_id': record_id, 'decision': 'reject',
                'reason': 'Current arithmetic can be established independently. api_key=unsafe-test-key'}]}

        self.enterContext(patch.dict(os.environ, {'INTERN_API_BASE': ENDPOINT}))
        self.open_star(
            deepcopy(REPLIES) + [choose_memory, deepcopy(REPLIES[1])] + [requests.Timeout('unknown')]
            + deepcopy(REPLIES[2:]),
            SHOWCASE_STAR_FEATURES={'problem_spec': True, 'final_generation': True,
                                    'final_solution_review': True, 'context_pack': True},
            SHOWCASE_STAR_CONTEXT_CAPACITY=CAPACITY_POLICY,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=12, max_http_attempts=12,
                max_tool_calls=0, max_tokens=100000, max_runtime_seconds=1100),
            SHOWCASE_FAITHFUL_MEMORY_ENABLED=True, SHOWCASE_POPULATION_MEMORY_ENABLED=True,
        )
        url = f'/api/sessions/{self.session}/memory/population/{self.session}'
        self.assertEqual(200, self.client.put(url + '/injection', json={'enabled': True},
                                              headers=self.headers()).status_code)
        def create():
            response = self.client.post('/api/agent/jobs', json={
                'message': PROBLEM, 'session_id': self.session,
                'solver_mode': 'star_limited', 'problem_spec': SPEC}, headers=self.headers())
            self.assertEqual(202, response.status_code, response.get_json())
            return response.get_json()['job_id']
        source = create()
        self.assertEqual('succeeded', self.terminal(source)['status'])
        target = create()
        failed = self.terminal(target)
        self.assertEqual('failed', failed['status'])
        before = len(self.outbound_messages)
        self.assertIn('population-memory-injection-v1', json.dumps(self.outbound_messages[-1]))
        with closing(sqlite3.connect(self.app.config['SHOWCASE_DATABASE_PATH'])) as db:
            old_state = json.loads(db.execute('SELECT state_json FROM solver_states WHERE run_id=?',
                                              (target,)).fetchone()[0])
        self.assertEqual(200, self.client.put(url + '/injection', json={'enabled': False},
                                              headers=self.headers()).status_code)
        unknown = failed['result']['solver']['recovery']['unknown_calls'][0]['call_id']
        resumed = self.client.post(f'/api/agent/jobs/{target}/resume', json={
            'retry_call': {'call_id': unknown, 'new_call_id': str(uuid.uuid4())}},
            headers=self.headers())
        self.assertEqual(202, resumed.status_code, resumed.get_json())
        final = self.terminal(target)
        self.assertEqual('succeeded', final['status'], final)
        self.assertEqual(failed['result']['budget']['deadline_at'], final['result']['budget']['deadline_at'])
        self.assertNotIn('population-memory-injection-v1', json.dumps(self.outbound_messages[before:]))
        with closing(sqlite3.connect(self.app.config['SHOWCASE_DATABASE_PATH'])) as db:
            state = json.loads(db.execute('SELECT state_json FROM solver_states WHERE run_id=?',
                                          (target,)).fetchone()[0])
        for call_id, record in old_state['calls'].items():
            self.assertEqual(record, state['calls'][call_id])
        self.assertTrue(any(call.get('population_memory_record_ids') for call in state['calls'].values()))
        decisions = [item for call in state['calls'].values() for item in call.get('memory_decisions', [])]
        self.assertEqual(['reject'], [item['decision'] for item in decisions])
        self.assertTrue(decisions[0]['reason'])
        from showcase.run_budget import public_solver_call_id
        response = self.client.get(f'/api/agent/jobs/{target}/memory')
        self.assertEqual(200, response.status_code)
        usage = response.get_json()['run_memory']['memory_usage']
        self.assertEqual(len(state['calls']), len(usage))
        by_alias = {item['call_id']: item for item in usage}
        for private_id, call in state['calls'].items():
            item = by_alias[public_solver_call_id(target, private_id)]
            self.assertEqual({'call_id', 'record_ids', 'decision_status', 'decisions'}, set(item))
            self.assertEqual(call.get('population_memory_record_ids', []), item['record_ids'])
            self.assertNotIn(private_id, json.dumps(usage))
        reported = [item for item in usage if item['decision_status'] == 'reported']
        self.assertEqual(1, len(reported))
        self.assertEqual(decisions, reported[0]['decisions'])
        self.assertNotIn('unsafe-test-key', json.dumps(usage))
        self.assertEqual(usage, self.client.get(f'/api/agent/jobs/{target}/memory').get_json()[
            'run_memory']['memory_usage'])

class Service179WorkerMemoryTest(unittest.TestCase):
    def test_parallel_worker_inherits_product_memory_enablement(self):
        from unittest.mock import patch

        from showcase.solver_harness.population_runtime import _work
        class WorkerReached(Exception):
            pass
        def inspect_worker(worker, *args):
            self.assertTrue(getattr(worker, '_population_memory_enabled', False))
            raise WorkerReached
        with SolverHarness(config={}) as parent:
            parent._population_memory_enabled = True
            with patch('showcase.solver_harness.population_route.RouteHarness', side_effect=inspect_worker):
                with self.assertRaises(WorkerReached):
                    _work(parent, ':memory:', 'run', 'route', 'action', '1+1')
