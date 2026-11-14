"""本地回执与原生实验报告的类型化来源解析，不授予子臂数学权威。"""
from collections.abc import Mapping


def resolve_report_source(state, step_id, report, plan_version, attempt_index, *, review=None):
    """先匹配本地 reasoner；原生来源必须绑定完成的父独立核验。"""
    from .proof_graph_sources import local_reasoner_report_call

    before = review.get('request_revision', -1) if review else None
    call_id = local_reasoner_report_call(state, step_id, report, plan_version, attempt_index, before)
    if call_id and state.get('native_report_sources'):
        reply = state['calls'][call_id].get('response', {})
        reply = reply.get('checkpoint', reply)
        if reply.get('argument') != report.get('argument'):
            call_id = None
    if call_id:
        return {'kind': 'local_call', 'source_id': call_id, 'call': state['calls'][call_id], 'report': report}
    return native_report_source(state, step_id, report, plan_version, attempt_index, review=review)


def native_report_source(state, step_id, report, plan_version, attempt_index, *, review):
    """验证明确绑定的原生报告，供父审查来源登记复用。"""
    from .serial_intervention import _digest

    if not isinstance(review, Mapping) or review.get('status') != 'completed' or review.get('role') != 'step_verifier':
        return None
    if (review.get('response', {}).get('verdict') != 'ACCEPT'
            or review.get('plan_version') != plan_version or review.get('attempt_index') != attempt_index
            or any(review.get(k) != state.get(k) for k in ('run_id', 'problem_hash', 'config_hash'))):
        return None
    request = review.get('request', {})
    if request.get('report') != report or request.get('step', {}).get('step_id') != step_id:
        return None
    for source_id, material in state.get('native_report_sources', {}).items():
        ref, call = material.get('reference', {}), material.get('call', {})
        if (source_id != 'native-report:' + _digest(material) or material.get('report') != report
                or ref.get('report_hash') != _digest(report)
                or ref.get('scope') != step_id or ref.get('plan_version') != plan_version
                or ref.get('specification_version') != state.get('specification_version')
                or ref.get('premises') != state.get('problem_spec', {}).get('assumptions', [])
                or ref.get('dependencies') != state.get('plan', {}).get('steps')
                or any(ref.get(k) != state.get(k) for k in ('run_id', 'problem_hash', 'config_hash'))
                or call.get('role') != 'reasoner' or call.get('status') != 'completed'
                or call.get('attempt_index') != attempt_index or call.get('plan_version') != plan_version
                or any(call.get(k) != state.get(k) for k in ('run_id', 'problem_hash', 'config_hash'))
                or call.get('request', {}).get('step', {}).get('step_id') != step_id):
            continue
        response = call.get('response', {})
        response = response.get('checkpoint', response)
        if (response.get('argument') != report.get('argument')
                or [c.get('statement') for c in response.get('claims', []) if isinstance(c, Mapping)]
                != [c.get('statement') for c in report.get('claims', []) if isinstance(c, Mapping)]):
            continue
        if not any(item.get('reference') == ref and item.get('report') == report
                   for item in request.get('intervention_results', []) if isinstance(item, Mapping)):
            continue
        return {'kind': 'native_reference', 'source_id': source_id, 'reference': ref,
                'report': report, 'call': call}
    return None


def native_material(engine, reference):
    """从持久子臂核对真实报告及回执，只封存来源材料，不导入其账本。"""
    import json

    from .faithful_intervention_records import FaithfulInterventionError
    from .proof_graph_sources import local_reasoner_report_call
    from .serial_intervention import result_reference

    if result_reference(engine, reference['pair_id'], reference['arm'], reference.get('result_id')) != reference:
        raise FaithfulInterventionError('native_report_source_changed')
    row = engine._connection.execute(
        'SELECT state_json FROM faithful_intervention_children WHERE pair_id=? AND arm=?',
        (reference['pair_id'], reference['arm'])).fetchone()
    child = json.loads(row[0])
    report = child['steps'][reference['scope']]['report']
    call_id = local_reasoner_report_call(child, reference['scope'], report, reference['plan_version'],
                                        child.get('attempt_index', 0))
    if call_id is None:
        raise FaithfulInterventionError('native_report_call_missing')
    return {'reference': reference, 'report': report, 'call': child['calls'][call_id]}
