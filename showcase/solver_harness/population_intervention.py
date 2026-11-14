"""把收敛后的合法串行视图接入干预，并将父任务核验成果回写所选路线。"""
import hashlib
from copy import deepcopy

from .autonomous_routes import serial_checkpoint_view
from .faithful_intervention_records import FaithfulInterventionError
from .population_store import _canonical
from .serial_intervention import _advance_serial

MATH_FIELDS = ('work_units', 'plan', 'plan_version', 'current_step', 'steps', 'accepted_results',
               'verified_results_ledger', 'progress', 'obligation_ledger',
               'obligation_evidence_ledger', 'active_assumptions')


def advance(harness, run, problem):
    from ..run_control import check_control
    check_control()
    state = run['state']
    intent = state.get('population_intervention') or {}
    if intent.get('status') == 'completed' or state.get('phase') == 'TERMINAL':
        return run
    if intent.get('status') == 'converging' and state.get('serial_intervention'):
        raise FaithfulInterventionError('population_intervention_already_used')
    if (not getattr(harness, '_intervention_enabled', False)
            or state.get('serial_intervention_permission') != {'enabled': True, 'version': 'serial-intervention-v1'}):
        return _blocked(harness, run, 'population_intervention_permission_revoked')
    if any(c.get('status') in {'unknown_outcome', 'dispatched'} for c in state.get('calls', {}).values()):
        return _blocked(harness, run, 'population_intervention_unknown_call')
    try:
        view = serial_checkpoint_view(state, expected_revision=run['state_revision'])
    except FaithfulInterventionError as error:
        return _blocked(harness, run, str(error))
    source = state['serial_checkpoint']
    if intent.get('status') == 'converging':
        run = harness.commit_event(run['run_id'], expected_revision=run['state_revision'],
            event={'event_id': f"population-intervention-ready-{run['state_revision']}",
                   'type': 'population_intervention_ready'},
            state_updates={**{k: deepcopy(view[k]) for k in MATH_FIELDS if k in view},
                           'phase': 'META_DECIDE',
                           'population_intervention': {'status': 'executing', 'source': deepcopy(source), 'origin': 'population', 'route_id': source['route_id'], 'source_version': source['snapshot_hash']}})
    elif intent.get('source') != source:
        return _blocked(harness, run, 'population_intervention_source_changed')
    run = _advance_serial(harness, run, problem)
    projection = run['state'].get('serial_intervention') or {}
    if projection.get('status') in {None, 'deciding', 'reserved', 'needs_review'}:
        return run
    check_control()
    from .population_store import command

    return command(harness, run['run_id'], 'intervention_complete',
                   expected_revision=run['state_revision'], updates=completion_updates(run['state']))


def completion_updates(state):
    """由父状态推导唯一合法回写，保留父核验、来源引用与父图，不复制子臂权威。"""
    source = state['population_intervention']['source']
    projection = state['serial_intervention']
    population = deepcopy(state['population'])
    route = population['routes'][source['route_id']]
    snapshot = deepcopy(route['snapshot'])
    snapshot.update({k: deepcopy(state[k]) for k in (*MATH_FIELDS, 'calls', 'proof_graph',
                                                    'native_report_sources') if k in state})
    snapshot.update(phase='STEP_EXECUTE' if state['phase'] == 'META_DECIDE' else state['phase'])
    route.update(snapshot=snapshot, revision=route['revision'] + 1)
    checkpoint = {**source, 'route_revision': route['revision'],
                  'snapshot_hash': hashlib.sha256(_canonical(snapshot).encode()).hexdigest(),
                  'revision': state['state_revision'] + 1}
    from .report_sources import native_report_source

    reviewed = {}
    for cid, call in state.get('calls', {}).items():
        request = call.get('request', {})
        source_record = native_report_source(state, request.get('step', {}).get('step_id'),
            request.get('report', {}), call.get('plan_version'), call.get('attempt_index'), review=call)
        if source_record and source_record['kind'] == 'native_reference':
            reviewed[cid] = hashlib.sha256(_canonical(call).encode()).hexdigest()
    return {'population': population, 'serial_checkpoint': checkpoint,
            'serial_checkpoint_snapshot': snapshot, 'phase': 'POPULATION',
            'execution_serial_sources': {**state.get('execution_serial_sources', {}), **reviewed},
            'population_intervention': {**state['population_intervention'], 'status': 'completed'},
            'serial_intervention': {**projection, 'origin': 'population',
                                   'route_id': source['route_id'], 'source_version': source['snapshot_hash']}}


def _blocked(harness, run, reason):
    """持久化阻断原因，禁止权限撤销或来源变化后继续派发。"""
    state = run['state']
    projection = {**state.get('serial_intervention', {}), 'status': 'needs_review',
                  'origin': 'population', 'reason': reason, 'continuation': 'pending'}
    if projection == state.get('serial_intervention'):
        return run
    return harness.commit_event(run['run_id'], expected_revision=run['state_revision'],
        event={'event_id': f"population-intervention-blocked-{run['state_revision']}",
               'type': 'population_intervention_blocked', 'reason': reason},
        state_updates={'serial_intervention': projection, 'population_intervention': {**state['population_intervention'], 'status': 'executing'}})
