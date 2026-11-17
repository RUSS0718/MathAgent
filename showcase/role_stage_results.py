"""Saved plan publications, bound at commit rather than inferred at read time."""
from copy import deepcopy
import hashlib
import hmac
import json
import re

from .faithful_public_progress import public_text

PLAN_IDENTITY = ('run_id', 'problem_hash', 'specification_version', 'plan_version', 'attempt_index')


def plan_source_ref(state, identity, event_id, body_version):
    return hmac.new(str(state.get('run_salt') or state['run_id']).encode(),
                    fingerprint([identity, event_id, body_version]).encode(), hashlib.sha256).hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def save_plan_source(state, updates, event):
    if event['type'] not in {'initial_plan_generated', 'plan_replaced'} or 'plan' not in updates:
        return updates, event
    current = {**state, **updates}
    plan = current['plan']
    from .solver_harness.plan import validate_plan

    validate_plan(plan)
    identity = {key: current.get(key) for key in PLAN_IDENTITY}
    body = [{key: step.get(key, [] if key == 'depends_on' else '')
             for key in ('step_id', 'title', 'objective', 'depends_on')} for step in plan['steps']]
    version = fingerprint(body)
    ref = plan_source_ref(state, identity, event['event_id'], version)
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
    expected_ref = plan_source_ref(state, {key: r.get(key) for key in PLAN_IDENTITY},
                                   r.get('event_id'), r['body_version'])
    if not hmac.compare_digest(r['source_ref'], expected_ref):
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


ROLE_ALIASES = {'reason_noncoding': 'reasoner', 'explore_polish': 'explore', 'meta_strategist': 'meta'}
ROLES = {'controller', 'planner', 'explore', 'reasoner', 'researcher', 'step_verifier',
         'whole_solution_verifier', 'final_generator', 'meta'}
METADATA = ('source_ref', 'plan_version', 'attempt_index', 'stage', 'body_version')


def canonical_role(role):
    return ROLE_ALIASES.get(role, role)


def save_committed_sources(state, updates, event):
    from .role_stage_findings import collect as findings
    from .role_stage_reviews import collect as reviews

    return save_role_sources(state, updates, event, collectors=(findings, reviews))


def _signature(state, record):
    payload = {key: value for key, value in record.items() if key != 'source_ref'}
    return hmac.new(str(state.get('run_salt') or state['run_id']).encode(),
                    fingerprint(payload).encode(), hashlib.sha256).hexdigest()


def save_role_sources(state, updates, event, collectors=()):
    """Publish only at the normal commit boundary, from the final merged state."""
    updates, event = save_plan_source(state, updates, event)
    current = {**state, **updates}
    records = list(current.get('role_stage_results', []))
    for collect in collectors:
        for publication in collect(current, event):
            role = canonical_role(publication['role'])
            if role not in ROLES:
                continue
            sections = [{key: public_text(section[key]) for key in ('label', 'text')}
                        for section in publication['sections']]
            check = {key: public_text(publication['check'][key]) for key in ('scope', 'status', 'label')}
            body_version = fingerprint([sections, check, publication['binding']])
            record = {**{key: current.get(key) for key in PLAN_IDENTITY},
                      'format': 'role-publication-v1', 'role': role, 'stage': publication['stage'],
                      'event_id': event['event_id'], 'sections': sections, 'items': [],
                      'body_version': body_version, 'check': {**check, 'body_version': body_version},
                      'binding': deepcopy(publication['binding'])}
            origin = _origin(current, record['binding'])
            if origin is not None:
                record['authority_version'] = _origin_version(origin)
            if isinstance(publication.get('summary'), str):
                record['summary'] = public_text(publication['summary'])
            else:
                summary = next((section['text'] for section in sections if section['label'] in {
                    '阶段结论', '阶段主张（待检查）', '候选结论（未检查）', '研究发现（未验证）',
                    '探索尝试（未验证）'}), None)
                if summary:
                    record['summary'] = summary
            record['source_ref'] = _signature(current, record)
            records.append(record)
            event = {**event, 'role_stage_source': record['source_ref'], 'role': role}
            if record.get('summary'):
                event = {**event, 'role_stage_summary': record['summary']}
    if records != current.get('role_stage_results', []):
        updates = {**updates, 'role_stage_results': records}
    return updates, event


def _valid_record(state, record):
    if (record.get('run_id') != state.get('run_id')
            or record.get('problem_hash') != state.get('problem_hash')
            or not isinstance(record.get('source_ref'), str)):
        return False
    if record.get('format') != 'role-publication-v1':
        return plan_results({**state, 'role_stage_results': [record]}, 'planner', record['source_ref'])['content_status'] == 'published'
    try:
        return hmac.compare_digest(record['source_ref'], _signature(state, record))
    except (ValueError, TypeError, KeyError):
        return False


def _validity(state, record, records):
    binding = record.get('binding', {})
    # Different attempts never borrow a current source body or its checks.
    current = all(record.get(key) == state.get(key) for key in PLAN_IDENTITY)
    if record.get('format') != 'role-publication-v1':
        return 'current' if current else 'replaced'
    if record.get('specification_version') != state.get('specification_version'):
        return 'invalidated'
    kind = binding.get('kind')
    call_id = binding.get('call_id') or binding.get('review_call_id') or binding.get('generator_call_id')
    if call_id:
        call = state.get('calls', {}).get(call_id)
        if not isinstance(call, dict) or call.get('run_id') != state.get('run_id') or call.get('status') != 'completed':
            return 'invalidated'
    origin = _origin(state, binding)
    if 'authority_version' in record:
        if origin is None or _revoked(origin):
            return 'invalidated'
        if record['authority_version'] != _origin_version(origin):
            return 'replaced'
    if kind == 'classified_result':
        ledger = state.get('verified_results_ledger', [])
        entries = [entry for entry in ledger if entry.get('result_id') == binding.get('result_id')]
        if len(entries) != 1 or not _live_result(state, entries[0], set()):
            return 'invalidated'
        entry = entries[0]
        rescued = any(r.get('result_id') == entry['result_id'] for r in state.get('rescued_results', []))
        if current or rescued:
            return 'current'
    if kind in {'step_report', 'step_review'}:
        step = state.get('steps', {}).get(binding.get('step_id'))
        if step is not None:
            if step.get('invalidated') is True:
                return 'invalidated'
            if binding.get('report_version') and fingerprint(step.get('report')) != binding['report_version']:
                return 'replaced'
            if kind == 'step_review':
                verification = step.get('checkpoint_verification') if binding.get('checkpoint_id') else step.get('verification')
                if binding.get('review_version') and fingerprint(verification) != binding['review_version']:
                    return 'invalidated' if isinstance(verification, dict) and verification.get('valid') is False else 'replaced'
    if kind == 'whole_review':
        from .final_evidence import artifact_identity

        reviews = state.get('whole_solution_reviews', [])
        if not reviews or reviews[-1].get('source') != binding.get('review_source'):
            return 'replaced'
        attempts = state.get('final_solution_attempts', [])
        if attempts and artifact_identity(attempts[-1].get('candidate', '')) != binding.get('candidate_artifact'):
            return 'replaced'
    if kind == 'meta' and isinstance(origin, dict) and origin.get('consumed') and not binding.get('consumed'):
        return 'historical'
    subject = _subject(record)
    later = [r for r in records[records.index(record) + 1:]
             if _subject(r) == subject]
    return 'replaced' if later or not current else 'current'


def _subject(record):
    binding = record.get('binding', {})
    return (record['role'], record['stage'], binding.get('step_id'),
            binding.get('result_id'), binding.get('round'), binding.get('task_id'),
            binding.get('verifier_call_id'))


def _origin(state, binding):
    """Resolve the producer's exact authority record without reading another body."""
    origin = binding.get('validity_origin')
    kind = binding.get('kind')
    if origin == 'steps':
        step = state.get('steps', {}).get(binding.get('step_id'))
        return step.get('report') if isinstance(step, dict) else None
    if kind == 'step_review':
        step = state.get('steps', {}).get(binding.get('step_id'), {})
        return step.get('checkpoint_verification') if binding.get('checkpoint_id') else step.get('verification')
    if origin in {'meta_decision', 'meta_guidance_decision'}:
        return state.get(origin)
    if origin == 'counterexample_checks':
        return state.get('steps', {}).get(binding.get('step_id'), {}).get('counterexample_checks', {}).get(binding.get('verifier_call_id'))
    selectors = {'exploration_findings': ('round', 'round'),
                 'reexploration_findings': ('task_id', 'task_id'),
                 'verified_results_ledger': ('result_id', 'result_id'),
                 'whole_solution_reviews': ('source', 'review_source'),
                 'final_solution_attempts': ('attempt', 'candidate_version')}
    if origin in selectors:
        key, binding_key = selectors[origin]
        matches = [item for item in state.get(origin, []) if item.get(key) == binding.get(binding_key)]
        return matches[0] if len(matches) == 1 else None
    return None


def _origin_version(origin):
    return fingerprint({key: value for key, value in origin.items()
                        if key not in {'valid', 'invalidated', 'invalidated_by_specification_version',
                                       'consumed', 'review', 'review_verdict'}})


def _revoked(origin):
    return (origin.get('invalidated') is True or origin.get('valid') is False
            or origin.get('invalidated_by_specification_version') is not None
            or isinstance(origin.get('runtime_qualification'), dict)
            and origin['runtime_qualification'].get('verdict') == 'REJECT')


def _live_result(state, entry, seen):
    """Apply the authoritative ledger's invalidation and dependency closure."""
    if (entry.get('result_id') in seen or entry.get('valid') is False
            or entry.get('invalidated') is True or entry.get('status') in {'INVALIDATED', 'invalidated'}):
        return False
    seen = seen | {entry.get('result_id')}
    graph = state.get('proof_graph')
    if isinstance(graph, dict):
        snapshots = [s for s in graph.get('snapshots', []) if s.get('graph_version') == graph.get('current_version')]
        if len(snapshots) != 1:
            return False
        snapshot = snapshots[0]
        linked = [a for a in snapshot.get('attempts', {}).values() if a.get('result_id') == entry.get('result_id')]
        if linked and not any(a.get('status') == 'accepted'
                              and snapshot.get('propositions', {}).get(a.get('conclusion'), {}).get('status') == 'supported'
                              and not snapshot['propositions'][a['conclusion']].get('conflict') for a in linked):
            return False
    for dependency in entry.get('dependencies', []):
        matches = [r for r in state.get('verified_results_ledger', []) if r.get('result_id') == dependency]
        if len(matches) == 1:
            if not _live_result(state, matches[0], seen):
                return False
        else:
            verification = state.get('steps', {}).get(dependency, {}).get('verification', {})
            if verification.get('valid') is not True or verification.get('verdict') != 'ACCEPT':
                return False
    return True


def role_results(state, role, source=None):
    """Read signed saved bodies, never synthesize a source from the latest state."""
    role = canonical_role(role)
    unavailable = {'content_status': 'unavailable', 'results': [], 'history': []}
    if role not in ROLES or not state or (source is not None and (
            not isinstance(source, str) or not re.fullmatch(r'[0-9a-f]{64}', source))):
        return unavailable
    records = state.get('role_stage_results', [])
    if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
        return unavailable
    wanted_role = 'planner' if role == 'controller' else role
    records = [r for r in records if r.get('role') == role or (role == 'controller'
               and r.get('role') == 'planner' and r.get('format') != 'role-publication-v1')]
    if any(not _valid_record(state, r) for r in records):
        return unavailable
    refs = [r['source_ref'] for r in records]
    if len(set(refs)) != len(refs):
        return unavailable
    history = [{**{key: r[key] for key in METADATA}, 'validity': _validity(state, r, records)} for r in records]
    matches = [r for r in records if r['source_ref'] == source] if source is not None else [
        r for r, metadata in zip(records, history) if metadata['validity'] == 'current']
    if not matches:
        return {**unavailable, 'history': history} if source is not None or wanted_role == 'planner' else {
            'content_status': 'empty', 'results': [], 'history': history}
    results = []
    for r in matches:
        metadata = next(h for h in history if h['source_ref'] == r['source_ref'])
        if r.get('format') != 'role-publication-v1':
            result = plan_results(state, role, r['source_ref'])['results'][0]
            results.append({**result, 'sections': []})
        else:
            result = {**metadata, 'check': dict(r['check']), 'items': [],
                      'sections': [dict(section) for section in r['sections']]}
            if 'summary' in r:
                result['summary'] = r['summary']
            results.append(result)
    return {'content_status': 'published', 'results': results, 'history': history}
