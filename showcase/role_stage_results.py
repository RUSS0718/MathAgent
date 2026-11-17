"""Saved plan publications, bound at commit rather than inferred at read time."""
import hashlib
import hmac
import json
import re

from .faithful_public_progress import public_text


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def save_plan_source(state, updates, event):
    if event['type'] not in {'initial_plan_generated', 'plan_replaced'} or 'plan' not in updates:
        return updates, event
    current = {**state, **updates}
    plan = current['plan']
    from .solver_harness.plan import validate_plan

    try:
        validate_plan(plan)
    except ValueError:
        return updates, event
    identity = {key: current.get(key) for key in
                ('run_id', 'problem_hash', 'specification_version', 'plan_version', 'attempt_index')}
    body = [{key: step.get(key, [] if key == 'depends_on' else '')
             for key in ('step_id', 'title', 'objective', 'depends_on')} for step in plan['steps']]
    version = fingerprint(body)
    ref = hmac.new(str(state.get('run_salt') or state['run_id']).encode(),
                   fingerprint([identity, event['event_id'], version]).encode(), hashlib.sha256).hexdigest()
    record = {**identity, 'role': 'planner', 'source_ref': ref, 'event_id': event['event_id'],
              'stage': 'planning', 'body_version': version, 'items': body,
              'check': {'scope': 'plan_structure', 'body_version': version}}
    return {**updates, 'role_stage_results': [*state.get('role_stage_results', []), record]}, {**event, 'role_stage_source': ref}


def plan_results(state, role, source=None):
    """Explicit identities only. Legacy snapshots never acquire invented provenance."""
    unavailable = {'content_status': 'unavailable', 'results': []}
    if source is not None and (not isinstance(source, str) or not re.fullmatch(r'[0-9a-f]{64}', source)):
        return unavailable
    records = state.get('role_stage_results', [])
    if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
        return unavailable
    records = [r for r in records if r.get('role') == 'planner']
    matches = [r for r in records if r.get('source_ref') == source] if source is not None else [
        r for r in records if all(r.get(k) == state.get(k) for k in
        ('run_id', 'problem_hash', 'specification_version', 'plan_version', 'attempt_index'))]
    if role not in {'planner', 'controller'} or len(matches) != 1:
        return unavailable
    r = matches[0]
    if not valid_plan_record(r):
        return unavailable
    if (r.get('run_id') != state.get('run_id') or r.get('problem_hash') != state.get('problem_hash')
            or fingerprint(r.get('items')) != r.get('body_version')
            or r.get('check') != {'scope': 'plan_structure', 'body_version': r.get('body_version')}):
        return unavailable
    current = all(r.get(k) == state.get(k) for k in ('specification_version', 'plan_version', 'attempt_index'))
    items = r['items']
    labels = {s['step_id']: f'步骤 {i}' for i, s in enumerate(items, 1)}
    public = [{'label': labels[s['step_id']], 'title': public_text(s['title']),
               'objective': public_text(s['objective']),
               'depends_on': [labels[d] for d in s['depends_on'] if d in labels]} for s in items]
    return {'content_status': 'published', 'results': [{
        **{k: r[k] for k in ('source_ref', 'plan_version', 'attempt_index', 'stage', 'body_version', 'check')},
        'validity': 'current' if current else 'replaced', 'items': public}]}


def valid_plan_record(record):
    """Malformed persisted sources are unavailable, never repaired by a read."""
    from .solver_harness.plan import validate_plan

    if (any(not isinstance(record.get(k), str) or not record[k] for k in ('run_id', 'problem_hash'))
            or any(type(record.get(k)) is not int for k in ('plan_version', 'attempt_index'))
            or record['plan_version'] < 1 or record['attempt_index'] < 0
            or record.get('stage') != 'planning'
            or any(not isinstance(record.get(k), str) or not re.fullmatch(r'[0-9a-f]{64}', record[k])
                   for k in ('body_version', 'source_ref'))):
        return False
    try:
        validate_plan({'version': record['plan_version'], 'steps': record.get('items')})
    except ValueError:
        return False
    return True
