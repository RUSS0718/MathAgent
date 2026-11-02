"""Public candidate history and deterministic replay; never expose solver requests."""
from copy import deepcopy

from .final_evidence import artifact_identity, bind_verification
from .redaction import redact
from .solver_harness.replay import replay_snapshot


def public_ref(value):
    return 'candidate-ref:' + artifact_identity(str(value))['sha256']


def public_grade(grade):
    return {key: deepcopy(grade[key]) for key in (
        'confidence_level', 'reason_codes', 'evidence_scope') if key in grade}


def public_candidate(record):
    result = {key: deepcopy(record[key]) for key in (
        'version', 'answer_text', 'answer_hash', 'source_phase', 'plan_version',
        'attempt_index', 'answer_completeness', 'review_state', 'selection_eligible')
        if key in record}
    result['candidate_id'] = public_ref(record['candidate_id'])
    for key in ('step_refs', 'dependency_refs', 'source_event_refs', 'evidence_refs', 'invalidated_by'):
        result[key] = [public_ref(value) for value in record.get(key, [])]
    result['evidence_grade'] = public_grade(record.get('evidence_grade', {}))
    return redact(result)


def public_decision(decision):
    if decision is None:
        return None
    result = {key: deepcopy(decision[key]) for key in (
        'status', 'confidence_level', 'reason_codes', 'selection_rule_version',
        'termination_reason') if key in decision}
    selected = decision.get('selected_source_record')
    result['selected_candidate_id'] = public_ref(selected['candidate_id']) if selected else None
    result['selected_candidate_version'] = selected['version'] if selected else None
    result['artifact'] = artifact_identity(selected['answer_text']) if selected else None
    result['excluded_candidate_ids'] = [public_ref(value) for value in decision['excluded_candidate_ids']]
    result['exclusion_reasons'] = {
        public_ref(key): deepcopy(value) for key, value in decision['exclusion_reasons'].items()}
    result['reason_evidence'] = {
        key: [public_ref(value) for value in values]
        for key, values in decision.get('reason_evidence', {}).items()}
    result['evidence_grade'] = public_grade(decision.get('evidence_grade', {}))
    return result


def candidate_projection(run):
    state = run['state']
    return {'candidate_history': [public_candidate(item) for item in state.get('candidate_registry') or []],
            'best_effort': public_decision(state.get('best_effort_decision'))}


def selection_verification(run, answer, verification):
    decision = run['state'].get('best_effort_decision')
    if decision is None:
        return verification
    selected = decision.get('selected_source_record')
    observation = bind_verification(answer, {
        'artifact': artifact_identity(selected['answer_text']) if selected else artifact_identity(answer),
        'status': 'unknown', 'scope': 'deterministic_candidate_selection',
        'checker_version': 'star-best-effort-v1', 'selection': public_decision(decision),
        'limitations': ['Deterministic selection is not mathematical proof.'],
    })['history'][0]
    return bind_verification(answer, {**observation, 'history': [
        *verification.get('history', []), observation]})


def replay_candidates(run):
    replay = replay_snapshot(run)
    return {'evidence_kind': 'replay', 'run_id': run['run_id'],
            'state_revision': run['state_revision'], 'audit': replay['audit'],
            'decision': public_decision(replay['decision'])}
