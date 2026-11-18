"""Allowlisted saved findings drafts; the storage owner signs and publishes them.

Only collect at normal mathematical save events with the final merged state.
Bindings are private provenance, never product labels. No report/argument body is
copied or hashed here; source calls and the allowlisted units identify the draft.
"""
from .faithful_public_progress import public_text
from .solver_harness.roles import session_role

_IDENTITY = ('run_id', 'problem_hash', 'specification_version', 'plan_version', 'attempt_index')


def _sections(record, fields):
    """Preserve whole string units; suppress sensitive units without truncation."""
    result = []
    for key, label in fields:
        values = record.get(key, [])
        values = [values] if isinstance(values, str) else values
        if not isinstance(values, list):
            continue
        for text in values:
            if isinstance(text, str) and text.strip():
                result.append({'label': label, 'text': public_text(text)})
    return result


def _call(state, predicate, roles):
    """Require one completed source with the same task, attempt and specification."""
    matches = []
    for key, call in state.get('calls', {}).items():
        if not isinstance(call, dict):
            continue
        request = call.get('request', {})
        if (call.get('call_id') != key or session_role(call.get('role')) not in roles
                or call.get('status') != 'completed'
                or any(call.get(k) != state[k] for k in
                       ('run_id', 'problem_hash', 'plan_version', 'attempt_index'))
                or not isinstance(request, dict)
                or request.get('problem_spec_version') != state['specification_version']
                or type(call.get('request_revision')) is not int
                or not isinstance(call.get('response'), dict)):
            continue
        if predicate(call):
            matches.append(call)
    return matches[0] if len(matches) == 1 else None


def _draft(state, event, call, role, stage, sections, check, **origin):
    return {'role': role, 'stage': stage, 'sections': sections, 'check': check,
            'binding': {**{k: state[k] for k in _IDENTITY},
                        'event_id': event['event_id'], 'call_id': call['call_id'],
                        'request_revision': call['request_revision'], **origin}}


def _claims(record):
    if not isinstance(record, dict):
        return []
    values = record.get('claims', [])
    if not isinstance(values, list):
        return []
    return [c if isinstance(c, str) else c.get('statement') if isinstance(c, dict) else None
            for c in values]


def _reasoner(state, event):
    step_id = event.get('step_id')
    step = state.get('steps', {}).get(step_id, {})
    if not isinstance(step, dict):
        return []
    report = step.get('report', {})
    if not isinstance(report, dict):
        return []
    call = _call(state, lambda c: c['request'].get('step', {}).get('step_id') == step_id
                 and isinstance(c['response'].get('checkpoint', c['response']), dict)
                 and _claims(c['response'].get('checkpoint', c['response'])) == _claims(report)
                 and c['request'].get('step', {}).get('objective') == report.get('objective')
                 and c['response'].get('checkpoint', c['response']).get('blocked')
                 == report.get('blocked'), {'reasoner'})
    if call is None:
        return []
    checkpoint = call['response'].get('checkpoint', {})
    if not isinstance(checkpoint, dict):
        return []
    if ('checkpoint_id' in event and (event['checkpoint_id'] != checkpoint.get('checkpoint_id')
                                     or event['checkpoint_id'] != step.get('checkpoint_id'))):
        return []
    sections = _sections(report, (('objective', '步骤目标'),))
    sections += _sections({'statements': _claims(report)},
                          (('statements', '阶段主张（待检查）'),))
    gaps = _sections(checkpoint, (('gaps', '未解决点'),))
    sections.extend(gaps)
    if report.get('blocked') is True and not gaps:
        sections.append({'label': '阻塞状态', 'text': '该步骤已记录阻塞，具体原因未记录'})
    draft = _draft(state, event, call, 'reasoner', 'step_submission', sections,
                   {'scope': 'step_submission', 'status': 'unreviewed',
                    'label': '该步骤提交的主张，待检查；不构成整题证明'},
                   step_id=step_id, checkpoint_id=checkpoint.get('checkpoint_id'),
                   validity_origin='steps')
    if not _claims(report):
        draft.update(sections=[], content_status='not_published')
    return [draft]


def _research(state, event):
    drafts = []
    tasks = state.get('reexploration_tasks', [])
    for finding in state.get('reexploration_findings', []):
        if not isinstance(finding, dict) or not isinstance(finding.get('output'), dict):
            continue
        task_id = finding.get('task_id')
        matched = [t for t in tasks if isinstance(t, dict) and t.get('task_id') == task_id
                   and t.get('status') == 'complete' and t.get('output_ref') == task_id]
        if not isinstance(task_id, str) or not task_id or len(matched) != 1:
            continue
        logical = f"research:{state['run_id']}:{task_id}"
        sessions = {logical}
        if state.get('run_salt') and state.get('config_hash'):
            from .solver_harness.sessions import session_identity

            sessions.add(session_identity(state, {'role': 'researcher',
                         'call_id': logical, 'session_key': logical})['session_key'])
        call = _call(state, lambda c: c.get('session_key') in sessions
                     and c['response'].get('findings') == finding['output'].get('findings'),
                     {'researcher'})
        sections = _sections(finding['output'], (('findings', '研究发现（未验证）'),))
        if call and sections:
            drafts.append(_draft(state, event, call, 'researcher', 'research', sections,
                          {'scope': 'research_findings', 'status': 'unreviewed',
                           'label': '该研究任务的发现，未验证；来源为已保存的任务产物'},
                          task_id=task_id, output_ref=task_id,
                          validity_origin='reexploration_findings',
                          provenance='unverified_exploration'))
    return drafts


def _counterexample(state, event):
    step_id = event.get('step_id')
    step = state.get('steps', {}).get(step_id, {})
    if not isinstance(step, dict) or not isinstance(step.get('counterexample_checks', {}), dict):
        return []
    matches = []
    for verifier_id, record in step.get('counterexample_checks', {}).items():
        if not isinstance(record, dict) or record.get('status') != 'completed':
            continue
        target, result = record.get('target', {}), record.get('result', {})
        if not isinstance(target, dict) or not isinstance(result, dict):
            continue
        index = target.get('claim_index')
        claims = _claims(step.get('report', {}))
        if (record.get('verifier_call_id') != verifier_id or type(index) is not int
                or not 0 <= index < len(claims) or claims[index] != target.get('claim')
                or result.get('verdict') not in {'NOT_FOUND', 'FOUND_COUNTEREXAMPLE'}
                or result.get('verdict') != event.get('counterexample_verdict')
                or not isinstance(result.get('searched_scope'), str)
                or not result['searched_scope'].strip()):
            continue
        review = _call(state, lambda c: c['call_id'] == verifier_id
                       and c['request'].get('step', {}).get('step_id') == step_id
                       and _claims(c['request'].get('report', {})) == claims,
                       {'step_verifier'})
        if review is None:
            continue
        call = _call(state, lambda c: c['call_id'] == record.get('call_id')
                     and c['request'].get('action') == 'counterexample_check'
                     and c['request'].get('claim') == target['claim']
                     and c['request'].get('assumptions') == target.get('assumptions')
                     and c['request'].get('forbidden_direction') == target.get('approach')
                     and all(c['response'].get(k) == result.get(k) for k in
                             ('verdict', 'counterexample', 'assumptions_checked',
                              'violated_conclusion', 'searched_scope')), {'researcher'})
        if call is None:
            continue
        sections = _sections(target, (('claim', '搜索对象'), ('assumptions', '适用条件')))
        sections += _sections(result, (('searched_scope', '反例搜索范围'),
                              ('assumptions_checked', '已考察条件'),
                              ('counterexample', '反例候选'),
                              ('violated_conclusion', '受质疑结论')))
        label = ('有限反例搜索未找到反例，不代表命题成立' if result['verdict'] == 'NOT_FOUND'
                 else '有限搜索提出反例候选，待核对；不构成整题审查')
        matches.append(_draft(state, event, call, 'researcher', 'counterexample_search', sections,
                       {'scope': 'counterexample_search', 'status': 'unreviewed', 'label': label},
                       step_id=step_id, verifier_call_id=verifier_id, claim_index=index,
                       validity_origin='counterexample_checks', verdict=result['verdict']))
    return matches if len(matches) == 1 else []


def _computation(state, finding, round_number):
    """Only complete textual outputs of matching executed finite receipts are public."""
    computation = finding.get('computation', {})
    if not isinstance(computation, dict) or computation.get('scope') != 'finite_computation':
        return [], []
    if not isinstance(computation.get('receipts', []), list):
        return [], []
    sections, receipt_ids = [], []
    for saved in computation.get('receipts', []):
        if not isinstance(saved, dict) or not isinstance(saved.get('receipt_id'), str):
            continue
        matches = [r for r in state.get('tool_receipts', []) if isinstance(r, dict)
                   and r.get('receipt_id') == saved['receipt_id']
                   and r.get('source_role') == 'explore' and r.get('step_id') is None
                   and r.get('review_round') == round_number
                   and r.get('attempt_index') == state['attempt_index']
                   and all(k not in r or r[k] == state[k] for k in _IDENTITY)
                   and r.get('executed') is True and r.get('status') == 'success'
                   and not r.get('unknown_outcome')
                   and r.get('output') == saved.get('output')]
        if len(matches) != 1:
            continue
        units = _sections(saved, (('output', '有限计算结果（仅覆盖该计算）'),))
        if units:
            sections.extend(units)
            receipt_ids.append(saved['receipt_id'])
    return sections, receipt_ids


def collect(state, event):
    """Return public-unit drafts only for the artifact committed by this event."""
    if (not isinstance(state, dict) or not isinstance(event, dict)
            or not isinstance(event.get('event_id'), str) or not event['event_id']
            or any(not isinstance(state.get(k), str) or not state[k]
                   for k in ('run_id', 'problem_hash'))
            or any(type(state.get(k)) is not int for k in
                   ('specification_version', 'plan_version', 'attempt_index'))
            or state['specification_version'] < 1 or state['plan_version'] < 0
            or state['attempt_index'] < 0
            or not isinstance(state.get('calls', {}), dict)
            or any(k in state and not isinstance(state[k], list) for k in
                   ('exploration_findings', 'reexploration_findings', 'reexploration_tasks',
                    'tool_receipts'))
            or not isinstance(state.get('steps', {}), dict)
            or any(k in event and event[k] != state[k] for k in _IDENTITY)):
        return []
    if (event.get('type') in {'step_reported', 'counterexample_completed'}
            and (not isinstance(event.get('step_id'), str) or not event['step_id'])):
        return []
    event_roles = {'step_reported': 'reasoner', 'explore_assessed': 'explore',
                   'reexploration_completed': 'researcher', 'counterexample_completed': 'researcher'}
    if 'role' in event and session_role(event['role']) != event_roles.get(event.get('type')):
        return []
    if event.get('type') == 'step_reported':
        return _reasoner(state, event)
    if event.get('type') == 'reexploration_completed':
        return _research(state, event)
    if event.get('type') == 'counterexample_completed':
        return _counterexample(state, event)
    if event.get('type') != 'explore_assessed':
        return []
    findings = [f for f in state.get('exploration_findings', [])
                if isinstance(f, dict) and f.get('round') == event.get('round')]
    if len(findings) != 1 or type(event.get('round')) is not int:
        return []
    finding = findings[0]
    source = finding.get('source', {})
    if not isinstance(source, dict) or source.get('status') == 'unknown':
        return []
    fields = (('worked', '探索尝试（未验证）'), ('failed', '受阻方向'),
              ('candidates', '候选结论（未检查）'))
    call = _call(state, lambda c: c['request'].get('round') == event['round']
                 and all(k not in source or source[k] == value for k, value in
                         (('call_id', c['call_id']), ('state_revision', c['request_revision']),
                          ('specification_version', state['specification_version']),
                          ('round', event['round'])))
                 and all(finding.get(k, []) == c['response'].get(k, []) for k, _ in fields),
                 {'explore'})
    if call is None:
        return []
    sections = _sections(finding, fields)
    computed, receipt_ids = _computation(state, finding, event['round'])
    sections.extend(computed)
    if not sections:
        return []
    return [_draft(state, event, call, 'explore', 'exploration', sections,
                   {'scope': 'exploration_candidate', 'status': 'unreviewed',
                    'label': '探索候选，未检查；不构成整题证明'},
                   round=event['round'], receipt_ids=receipt_ids,
                   validity_origin='exploration_findings',
                   provenance='unverified_exploration')]
