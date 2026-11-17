"""Saved plan publications, bound at commit rather than inferred at read time."""
import hashlib
import hmac
import json

from .faithful_public_progress import public_text


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def save_plan_source(state, updates, event):
    if event['type'] not in {'initial_plan_generated', 'plan_replaced'} or 'plan' not in updates:
        return updates, event
    current = {**state, **updates}
    plan = current['plan']
    if not isinstance(plan, dict) or not plan.get('steps'):
        return updates, event
    identity = {key: current.get(key) for key in
                ('run_id', 'problem_hash', 'specification_version', 'plan_version', 'attempt_index')}
    body = [{key: step.get(key, [] if key == 'depends_on' else '')
             for key in ('step_id', 'title', 'objective', 'depends_on')} for step in plan['steps']]
    version = fingerprint(body)
    ref = hmac.new(str(state.get('run_salt') or state['run_id']).encode(),
                   fingerprint([identity, event['event_id'], version]).encode(), hashlib.sha256).hexdigest()
    record = {**identity, 'source_ref': ref, 'event_id': event['event_id'],
              'stage': 'planning', 'body_version': version, 'items': body,
              'check': {'scope': 'plan_structure', 'body_version': version}}
    return {**updates, 'role_stage_results': [*state.get('role_stage_results', []), record]}, {**event, 'role_stage_source': ref}


def plan_results(state, role, source=None):
    """Explicit identities only. Legacy snapshots never acquire invented provenance."""
    records = state.get('role_stage_results', [])
    matches = [r for r in records if r.get('source_ref') == source] if source else [
        r for r in records if all(r.get(k) == state.get(k) for k in
        ('run_id', 'problem_hash', 'specification_version', 'plan_version', 'attempt_index'))]
    if role not in {'planner', 'controller'} or len(matches) != 1:
        return {'content_status': 'unavailable', 'results': []}
    r = matches[0]
    if (r.get('run_id') != state.get('run_id') or r.get('problem_hash') != state.get('problem_hash')
            or fingerprint(r.get('items')) != r.get('body_version')
            or r.get('check') != {'scope': 'plan_structure', 'body_version': r.get('body_version')}):
        return {'content_status': 'unavailable', 'results': []}
    current = all(r.get(k) == state.get(k) for k in ('specification_version', 'plan_version', 'attempt_index'))
    items = r['items']
    labels = {s['step_id']: f'步骤 {i}' for i, s in enumerate(items, 1)}
    public = [{'label': labels[s['step_id']], 'title': public_text(s['title']),
               'objective': public_text(s['objective']),
               'depends_on': [labels[d] for d in s['depends_on'] if d in labels]} for s in items]
    return {'content_status': 'published', 'results': [{
        **{k: r[k] for k in ('source_ref', 'plan_version', 'attempt_index', 'stage', 'body_version', 'check')},
        'validity': 'current' if current else 'replaced', 'items': public}]}
