"""Structural stream cost and durable audit behavior at the public Harness seam."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from showcase.solver_harness import SolverHarness
from showcase.solver_harness.calls import CallInterrupted
from showcase.stream_activity import notify


class StreamAuditScalingTest(unittest.TestCase):
    def test_interleaved_commit_and_crash_keep_history_partial_and_unknown(self):
        class Crash(BaseException):
            pass

        config = {'max_model_calls': 4,
                  'features': {'stream_recovery': True, 'stream_activity': True}}
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'crash.sqlite3'
            with SolverHarness(database_path=database, config=config) as harness:
                run = harness.solve('question', {'run_id': 'crash'})

                def operation(request):
                    yield {'type': 'text_delta', 'text': 'one'}
                    current = harness.get_run('crash')
                    harness.commit_event(
                        'crash', expected_revision=current['state_revision'],
                        event={'event_id': 'interleaved', 'type': 'checkpoint'},
                    )
                    notify(request['activity_observer'], 'content', content_bytes=6)
                    yield {'type': 'text_delta', 'text': 'two'}
                    self.assertIn('interleaved', [e['event_id'] for e in run['events']])
                    raise Crash()

                request = {'run_id': 'crash', 'role': 'explore',
                           'call_id': 'interrupted', 'problem': 'question'}
                with self.assertRaises(Crash):
                    harness.dispatch(run, operation, request)
            with SolverHarness(database_path=database, config=config) as recovered:
                saved = recovered.get_run('crash')
                call = saved['state']['calls']['interrupted']
                self.assertEqual('onetwo', call['partial_text'])
                self.assertEqual('unknown_outcome', call['status'])
                self.assertNotIn('response', call)
                self.assertFalse(saved['state'].get('final_response'))
                self.assertFalse(saved['state'].get('candidate_registry'))
                def forbidden(request):
                    self.fail('unknown call was automatically retried')
                with self.assertRaises(CallInterrupted):
                    recovered.dispatch(saved, forbidden, request)

    def test_equal_streams_do_not_rematerialize_accumulated_history(self):
        fragments = 16
        decoded_events = []
        loads = json.loads

        def measure(value, *args, **kwargs):
            result = loads(value, *args, **kwargs)
            if isinstance(result, dict) and 'event_id' in result and 'run_id' in result:
                decoded_events.append(result['event_id'])
            return result

        delivered = []
        snapshots = []
        delta_costs = []

        def observe(run, event):
            self.assertIsInstance(run['events'], list)
            json.dumps(run)
            delivered.append(dict(event))
            # Observers can retain a historical snapshot without later appends changing it.
            snapshots.append((run['events'], len(run['events'])))

        class Port:
            calls = 0

            def complete(self, request):
                self.calls += 1
                for index in range(fragments):
                    before = len(decoded_events)
                    notify(request['activity_observer'], 'event', event_count=index + 1)
                    notify(request['activity_observer'], 'content', content_bytes=index + 1)
                    yield {'type': 'text_delta', 'text': 'x'}
                    delta_costs.append(len(decoded_events) - before)
                yield {'type': 'result', 'result': {'assessment': 'NEED_PLAN'}}

        config = {'max_model_calls': 4,
                  'features': {'stream_recovery': True, 'stream_activity': True}}
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'stream.sqlite3'
            port = Port()
            with SolverHarness(database_path=database, config=config,
                               event_observer=observe) as harness:
                run = harness.solve('question', {'run_id': 'scaling'})
                costs = []
                with patch('json.loads', side_effect=measure):
                    for call_id in ('first', 'second'):
                        before = len(decoded_events)
                        harness.dispatch(run, port.complete, {
                            'run_id': run['run_id'], 'role': 'explore',
                            'call_id': call_id, 'problem': 'question',
                        })
                        costs.append(len(decoded_events) - before)
                for call_id in ('first', 'second'):
                    call = run['state']['calls'][call_id]
                    self.assertEqual('completed', call['status'])
                    self.assertEqual('x' * fragments, call['partial_text'])
                    self.assertEqual(fragments, call['stream_metrics']['event_count'])
                self.assertEqual(2, port.calls)
                self.assertEqual(run['events'], delivered)
                self.assertEqual(len(delivered), len({e['event_id'] for e in delivered}))
                self.assertEqual(sorted(e['state_revision'] for e in delivered),
                                 [e['state_revision'] for e in delivered])
                self.assertTrue(all(len(events) == size for events, size in snapshots))
                for events, size in snapshots:
                    self.assertEqual(delivered[:size], list(events))
                saved = harness.get_run(run['run_id'])
            with SolverHarness(database_path=database, config=config) as reopened:
                self.assertEqual(saved, reopened.get_run('scaling'))
            # A fixed number of whole-call boundary reads is acceptable; per-delta
            # reloads are not. Doubling history must not multiply stream work.
            print(f'stream_history_event_decodes={costs}')
            print(f'per_delta_event_decodes={delta_costs}')
            self.assertLessEqual(max(costs), 16 * len(delivered), costs)
            self.assertEqual([0] * (2 * fragments), delta_costs)


if __name__ == '__main__':
    unittest.main()
