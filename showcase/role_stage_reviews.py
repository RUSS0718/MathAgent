"""Frozen, allowlisted review drafts from the normal committed save boundary.

The caller owns signing, persistence and current validity. No reads here execute
roles/tools or infer mathematical evidence from lifecycle events.
"""
from copy import deepcopy

from .faithful_public_progress import public_text
from .final_evidence import artifact_identity
from .role_stage_results import fingerprint
from .solver_harness.classified import CATEGORIES
from .solver_harness.final_binding import review_binding
from .solver_harness.protocol_repair import completed_call_id


def _sections(*pairs):
    return [{'label': label, 'text': public_text(text)} for label, text in pairs
            if isinstance(text, str) and text.strip()]


def _draft(role, stage, sections, scope, status, label, binding):
    return deepcopy({'role': role, 'stage': stage, 'sections': sections,
                     'check': {'scope': scope, 'status': status, 'label': label},
                     'binding': binding})


def _current_call(state, call, role):
    return (call.get('role') == role and call.get('status') == 'completed'
            and call.get('run_id') == state.get('run_id')
            and all(call.get(k) == state.get(k) for k in ('plan_version', 'attempt_index'))
            and ('specification_version' not in call
                 or call['specification_version'] == state.get('specification_version'))
            and not call.get('response', {}).get('tool_request'))


def _step(state, event):
    step_id = event.get('step_id')
    step = state.get('steps', {}).get(step_id, {})
    verification = step.get('checkpoint_verification') if event.get('checkpoint_id') else step.get('verification')
    if not isinstance(verification, dict) or not isinstance(step.get('report'), dict):
        return []
    gates = ('verdict', 'goal_gate', 'logic_gate', 'valid')
    if any(event.get(k) != verification.get(k) for k in gates):
        return []
    candidates = [(key, call) for key, call in state.get('calls', {}).items()
                  if _current_call(state, call, 'step_verifier')
                  and call.get('request', {}).get('step', {}).get('step_id') == step_id
                  and call.get('request', {}).get('report') == step.get('report')
                  and all(call.get('response', {}).get(k) == verification.get(k)
                          for k in ('verdict', 'goal_gate', 'logic_gate'))
                  and (not event.get('checkpoint_id') or
                       call.get('request', {}).get('checkpoint', {}).get('checkpoint_id') == event['checkpoint_id'])]
    if not candidates:
        return []
    revision = max(c.get('request_revision', -1) for _, c in candidates)
    candidates = [(key, c) for key, c in candidates if c.get('request_revision', -1) == revision]
    if len(candidates) != 1:
        return []
    call_id, call = candidates[0]
    objective = call['request']['step'].get('objective')
    binding = {'kind': 'step_review', 'step_id': step_id, 'review_call_id': call_id,
               'request_revision': revision, 'report_version': fingerprint(step['report']),
               'review_version': fingerprint(verification),
               'checkpoint_id': event.get('checkpoint_id')}
    valid = verification.get('valid') is True
    status = 'accepted' if valid and verification.get('verdict') == 'ACCEPT' else 'rejected' if valid else 'unknown'
    drafts = [_draft('step_verifier', 'step_review', _sections(
        ('检查对象', objective), ('未解决点', verification.get('objection')),
        ('检查说明', '步骤模型检查仅适用于所列步骤目标，不代表整题证明。')),
        'step_model_review', status, '步骤模型检查（仅限本步目标）', binding)]
    labels = {'Lemma': '引理', 'Conjecture': '猜想', 'Computation': '计算结果',
              'Definition': '定义', 'Answer': '答案候选'}
    levels = {'conjecture': '猜想，尚未证明', 'llm_reviewed': '模型审查',
              'tool_verified': '有限计算检查'}
    for entry in state.get('verified_results_ledger', []):
        if (entry.get('source') != step_id or entry.get('review_call_id') != call_id
                or entry.get('category') not in CATEGORIES
                or not entry.get('result_id')
                or ('specification_version' in entry
                    and entry['specification_version'] != state.get('specification_version'))
                or any(entry.get(k) != state.get(k) for k in ('plan_version', 'attempt_index'))):
            continue
        category, level = entry['category'], entry.get('evidence_level')
        conjecture = category == 'Conjecture'
        supported = ((category == 'Computation' and level == 'tool_verified')
                     or (category != 'Computation' and level == 'llm_reviewed'))
        scoped = isinstance(entry.get('scope'), str) and bool(entry['scope'].strip())
        check_status = 'unreviewed' if conjecture else 'accepted' if supported and scoped else 'unknown'
        drafts.append(_draft('step_verifier', 'classified_result', _sections(
            ('分类', labels[category]), ('证据等级', '猜想，尚未证明' if conjecture else levels.get(level, '未知')),
            ('阶段结论', entry.get('statement')), ('适用范围', entry.get('scope')),
            ('未解决点', verification.get('objection')),
            ('检查说明', '仅限该条分类成果及其适用范围；有限计算不构成普遍证明。')),
            'conjecture' if conjecture else 'finite_computation' if level == 'tool_verified' else 'classified_model_review',
            check_status, '猜想，未证明' if conjecture else '有限计算抽查（仅限所列范围）'
            if level == 'tool_verified' else '单条成果模型检查（仅限所列范围）',
            {**binding, 'kind': 'classified_result', 'validity_origin': 'verified_results_ledger',
             'result_id': entry['result_id'], 'result_version': fingerprint(entry),
             'receipt_ids': entry.get('receipt_ids', []), 'dependencies': entry.get('dependencies', [])}))
    return drafts


def _whole(state, event):
    records = state.get('whole_solution_reviews', [])
    if not records:
        return []
    record = records[-1]
    source = record.get('source', {})
    call = state.get('calls', {}).get(source.get('call_id'), {})
    candidate = call.get('request', {}).get('solution_candidate', '')
    run = {'run_id': state.get('run_id'), 'state': state, 'events': [event]}
    meaning = review_binding(run, candidate)
    status = (meaning['whole_review'] if meaning['binding'] == 'same_artifact' else 'unknown')
    if status not in {'accepted', 'rejected'}:
        status = 'unknown'
    criteria = {'original_problem_consistency': '原题一致性', 'completeness': '完整性',
                'cross_step_logic': '跨步骤逻辑', 'output_format': '输出格式'}
    covered = [criteria[k] for k in call.get('request', {}).get('review_criteria', []) if k in criteria]
    gaps = sum(item.get('status') != 'satisfied' for item in state.get('obligation_ledger', []))
    return [_draft('whole_solution_verifier', 'whole_review', _sections(
        ('阶段结论', '整题模型审查通过。' if status == 'accepted' else '整题模型审查未通过。'
         if status == 'rejected' else '整题模型审查来源或候选绑定未确认。'),
        ('覆盖目标', '；'.join(covered) if covered else '未记录具体覆盖目标。'),
        ('未解决点', f'仍有 {gaps} 项根目标未完成核验。' if gaps else '未记录可公开的审查缺口摘要。'),
        ('检查说明', '仅检查该版本候选；模型审查不构成数学正确性或完整性的形式证明。')),
        'whole_solution_llm_review', status,
        '整题模型审查通过（仅限所列候选与覆盖目标）' if status == 'accepted' else
        '整题模型审查未通过' if status == 'rejected' else '整题模型审查未知（来源未确认）',
        {'kind': 'whole_review', 'validity_origin': 'whole_solution_reviews',
         'review_source': source, 'candidate_artifact': record.get('artifact'),
         'request_candidate_artifact': artifact_identity(candidate),
         'review_version': fingerprint(record), 'binding_status': meaning['binding']})]


def _generator(state):
    attempts = state.get('final_solution_attempts', [])
    if not attempts:
        return []
    attempt = attempts[-1]
    if (any(attempt.get(k) != state.get(k)
            for k in ('plan_version', 'attempt_index', 'specification_version'))
            or attempt.get('invalidated') or attempt.get('invalidated_by_specification_version')):
        return []
    session = attempt.get('session_key')
    if not isinstance(session, str) or not session.strip():
        return []
    # finalize.finalization_requests binds the logical session to this call root.
    # The request session itself is rewritten by the native role-session layer.
    calls = state.get('calls', {})
    key = completed_call_id(calls, f'final-generator:{session}')
    call = calls.get(key, {})
    if (not _current_call(state, call, 'final_generator')
            or call.get('call_id') != key or call.get('request', {}).get('call_id') != key
            or call.get('request', {}).get('problem_spec_version') != state.get('specification_version')
            or not isinstance(attempt.get('candidate'), str) or not attempt['candidate'].strip()
            or call.get('response', {}).get('final_response') != attempt['candidate']):
        return []
    return [_draft('final_generator', 'final_candidate', _sections(
        ('阶段结论', '已保存终稿候选，生成成功不代表检查通过。'),
        ('检查说明', '候选被采用或任务结束不提升证据等级；检查结果以独立审查记录为准。')),
        'candidate_generation', 'unreviewed', '终稿候选生成（不提供证明）',
        {'kind': 'final_candidate', 'validity_origin': 'final_solution_attempts',
         'generator_call_id': key, 'request_revision': call.get('request_revision'),
         'candidate_version': attempt.get('attempt'), 'candidate_artifact': artifact_identity(attempt['candidate']),
         'candidate_record_version': fingerprint(attempt)})]


_ACTIONS = {'CONTINUE': '继续当前求解', 'TRACE_BACK': '回溯已有步骤',
            'APPROVE_REPLAN': '批准重新规划', 'ABORT': '终止当前求解',
            'explore_more': '建议补充探索', 'retry_different_method': '建议换一种方法重试',
            'trace_back': '建议回溯已有步骤', 'replan': '建议重新规划，仍需独立决议。'}
_EXECUTED = {'plan_archived': '归档旧计划，准备重新规划。',
             'trace_back_applied': '回溯并更新受影响成果。',
             'meta_guidance_applied': '已将建议任务交给求解角色。'}


def _meta(state, event):
    kind = event['type']
    applied = kind in _EXECUTED
    guidance = kind in {'meta_guidance_decided', 'meta_guidance_applied'}
    keys = ('meta_guidance_decision', 'meta_decision') if applied else (
        ('meta_guidance_decision',) if guidance else ('meta_decision',))
    drafts = []
    for key in keys:
        decision = state.get(key)
        if not isinstance(decision, dict) or decision.get('run_id') != state.get('run_id'):
            continue
        action = decision.get('action_type') if key == 'meta_guidance_decision' else decision.get('decision')
        if action not in _ACTIONS or type(decision.get('decided_at_revision')) is not int:
            continue
        consumption = decision.get('consumed') or {}
        if applied:
            if (consumption.get('event_type') != kind
                    or consumption.get('state_revision') != event.get('state_revision')
                    or event.get('decision_revision') != decision['decided_at_revision']):
                continue
        elif (any(decision.get(k) != state.get(k) for k in ('plan_version', 'attempt_index'))
              or (guidance and event.get('action_type') != action)
              or (not guidance and event.get('decision') != {k: v for k, v in decision.items()
                  if k in {'decision', 'reason_summary', 'plan_summary', 'forbidden_directions', 'reusable_results', 'trace_back_to'}})):
            continue
        failures = {'stuck': '当前求解停滞', 'timeout': '执行超时', 'code_issue': '代码执行遇到障碍'}
        drafts.append(_draft('meta', 'meta_execution' if applied else 'meta_guidance' if guidance else 'meta_decision',
            _sections(('建议' if key == 'meta_guidance_decision' else '决议', _ACTIONS[action]),
                      ('执行状态', '已执行：' + _EXECUTED[kind] if applied else '已保存，尚未记录后续执行。'),
                      ('障碍', failures.get(decision.get('failure_type'), '未记录可公开的障碍摘要。')),
                      ('适用范围', '当前求解调度；策略决议不是数学成果或证明。')),
            'strategy_execution' if applied else 'strategy_decision', 'unreviewed', '策略记录（不提供数学证明）',
            {'kind': 'meta', 'validity_origin': key, 'step_id': decision.get('step_id'),
             'decision_revision': decision['decided_at_revision'], 'decision_version': fingerprint(decision),
             'plan_version': decision.get('plan_version'), 'attempt_index': decision.get('attempt_index'),
             'consumed': consumption if applied else None}))
    return drafts


def _formal(state, event):
    from .formal_requirements import assess_formal_requirement
    from .formal_specification import normalize_target, public_target
    from .solver_harness.formal_integration import project_formal_verification

    record = project_formal_verification(state)
    if not record or not isinstance(record.get('current'), dict):
        return []
    current = record['current']
    if (current.get('attempt_id') != record.get('current_attempt_id')
            or event.get('status') != record.get('status')
            or event.get('grade') != record.get('grade')):
        return []
    try:
        target = public_target(normalize_target(record.get('policy', {}).get('target')))
    except (TypeError, ValueError):
        return []
    # Reuse the existing receipt assessor. A local L2/L3 receipt is intentionally
    # displayed at its exact target scope, never promoted to original-problem proof.
    assessment = assess_formal_requirement({**record.get('policy', {}), 'target': target,
        'require_formal': True, 'requirement': {'scope': 'formal_target', 'minimum_grade': 'L2',
                                             'target_hash': target['hash']}}, record)
    spec = current.get('specifications', {}).get('original_to_spec', {})
    accepted = (assessment['status'] == 'met'
                and spec.get('problem_spec_version') == state.get('specification_version'))
    status = 'accepted' if accepted else 'rejected' if record.get('status') == 'failed' else 'unknown'
    return [_draft('whole_solution_verifier', 'formal_target_review', _sections(
        ('形式目标', f"对任意有理数 {target['variables'][0]}，{target['lhs']} = {target['rhs']}"),
        ('检查说明', '仅核验所列形式目标；不据此宣称原题或全部目标已证明。')),
        'local_formal_target', status, '局部形式目标检查通过' if accepted else '局部形式目标检查未确认',
        {'kind': 'formal_target', 'validity_origin': 'formal_verification',
         'formal_attempt_id': current['attempt_id'], 'target_hash': target['hash'],
         'formal_record_version': fingerprint(current),
         'specification_version': spec.get('problem_spec_version')})]


def collect(state, event):
    """Collect only this saved event's structured sources; never infer from status."""
    if event.get('type') == 'step_reviewed':
        return _step(state, event)
    if event.get('type') in {'final_candidate_reviewed', 'solution_review_assessed'}:
        return _whole(state, event)
    if event.get('type') == 'final_candidate_generated':
        return _generator(state)
    if event.get('type') in {'meta_decided', 'meta_guidance_decided', *_EXECUTED}:
        return _meta(state, event)
    if event.get('type') == 'formal_verification_completed':
        return _formal(state, event)
    return []
