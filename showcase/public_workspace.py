"""Explicit ordinary workspace DTOs. Never copy unknown nested metadata."""
import hashlib
from collections.abc import Mapping

from .redaction import redact_text


def obj(value):
    return value if isinstance(value, Mapping) else {}


def fields(value, names):
    value = obj(value)
    return {key: redact_text(value[key]) if isinstance(value[key], str) else value[key]
            for key in names if key in value and type(value[key]) in (str, int, bool, float, type(None))}


def opaque(value):
    return hashlib.sha256(str(value).encode()).hexdigest()[:20]


def solver_view(value):
    value = obj(value)
    progress = obj(value.get('progress'))
    steps = progress.get('steps')
    result = fields(value, ('phase',))
    result['progress'] = fields(progress, ('plan_version',))
    if isinstance(steps, list):
        result['progress']['steps'] = [fields(step, ('label','goal_summary','current','reported','verdict','valid'))
                                       for step in steps if isinstance(step, Mapping)]
    return result


def result_view(value):
    value = obj(value)
    result = fields(value, ('presentation_mode',))
    mode = value.get('execution_mode')
    if mode in {'fake', 'live', 'unavailable'}:
        result['execution_mode'] = mode
    elif isinstance(mode, str) and mode.startswith('star'):
        result['execution_mode'] = 'live'
    if isinstance(value.get('solver'), Mapping):
        result['solver'] = solver_view(value['solver'])
    faithful = obj(value.get('faithful'))
    if faithful:
        safe = fields(faithful, ('phase','revision_allowed','input_version'))
        safe['allowed_actions'] = [a for a in faithful.get('allowed_actions', [])
                                   if a in {'cancel','resume','clarify','answer','revise','new_task','retry','pause','resume_intervention','retry_unknown_call','create_new_task','save_clarification','answer_clarification'}]
        if faithful.get('reason'):
            safe['reason'] = '请查看任务状态及可用操作；结果未知时请先核对原任务。'
        for key in ('revision_to','revision_source'):
            if key in faithful:
                safe[key] = fields(faithful[key], ('task_id',))
        if 'clarification' in faithful:
            safe['clarification'] = fields(faithful['clarification'],
                ('request_id','task_id','input_version','question','status','answer'))
            safe['clarification']['reason'] = '请补充题目条件。'
        result['faithful'] = safe
    return result


def job_view(value):
    safe = fields(value, ('success','job_id','session_id','status','updated_at','input_user_file_id',
                         'last_event_id','existing','new_session_id','presentation_mode','task_id','continuation','input_version'))
    if 'faithful' in value:
        safe.update(result_view({'faithful': value['faithful']}))
    if 'result' in value:
        safe['result'] = result_view(value['result'])
    return safe


def event_data(event):
    raw = obj(event.get('data'))
    safe = fields(raw, ('role','stage','phase','status','created_at','step_id','solver_event_type',
                       'call_lifecycle','call_status','plan_version','attempt_index','verdict','valid'))
    safe['type'] = event['event']
    kind = raw.get('solver_event_type')
    routing = {
        'objective_dependencies': '题目中的目标有先后依赖，先制定分步方案。',
        'initial_explore_output_limit': '本次探索达到输出上限，转入制定方案。',
        'initial_explore_incomplete': '本次探索未完成，转入制定方案。',
    }
    if kind == 'adaptive_planning_required' and raw.get('reason') in routing:
        safe['routing_summary'] = routing[raw['reason']]
    elif kind == 'explore_assessed':
        routes = {
            ('SOLVED', 'EXPLORE_REVIEW'): '已形成完整候选，交由独立答案审查。',
            ('NEED_PLAN', 'PLAN'): '探索表明需要分步处理，转入制定方案。',
            ('PARTIALLY_SOLVED', 'PLAN'): '已取得部分进展，转入分步求解。',
            ('UNKNOWN', 'PLAN'): '本次探索尚不能形成完整答案，转入制定方案。',
            ('PARTIALLY_SOLVED', 'EXPLORE'): '已取得部分进展，继续探索。',
        }
        summary = routes.get((raw.get('assessment'), raw.get('next_phase')))
        if summary:
            safe['routing_summary'] = summary
    if 'solver_call_id' in raw:
        safe['solver_call_id'] = opaque(raw['solver_call_id'])
    if isinstance(raw.get('solver'), Mapping):
        safe['solver'] = solver_view(raw['solver'])
    if isinstance(raw.get('role_stage_source'), str):
        safe['role_stage_source'] = raw['role_stage_source']
        if isinstance(raw.get('role_stage_summary'), str):
            from .faithful_public_progress import public_text

            safe['role_stage_summary'] = public_text(raw['role_stage_summary'])
    workbench = obj(raw.get('workbench'))
    if workbench:
        safe['workbench'] = fields(workbench, ('version','kind','from_role','to_role','summary','step_label',
            'plan_version','attempt_index','content_status','thread_status','chosen'))
        for key in ('message_id','thread_id'):
            if key in workbench:
                safe['workbench'][key] = opaque(workbench[key])
        if isinstance(workbench.get('changes'), list):
            safe['workbench']['changes'] = [fields(c, ('op','step_label','summary')) for c in workbench['changes']]
    safe['summary'] = '求解进展已更新。'
    return safe
