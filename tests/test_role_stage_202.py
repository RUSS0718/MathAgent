"""Synthetic saved-state contracts; no solver, model or tool execution."""
import copy
import json
import unittest

from showcase.formal_specification import normalize_target, public_target
from showcase.role_stage_reviews import collect
from showcase.solver_harness.classified import build_entries
from showcase.solver_harness.final_binding import review_record
from showcase.solver_harness.finalize import finalization_requests


def generator_state():
    session = 'final:run:plan1:attempt0:candidate0'
    request, _ = finalization_requests('problem', [], [], session, None, False)
    request.update(session_key='run:salt:final_generator:1:None:0', problem_spec_version=1)
    call_id = request['call_id']
    return {'run_id': 'run', 'plan_version': 1, 'attempt_index': 0,
            'specification_version': 1,
            'final_solution_attempts': [{'attempt': 0, 'plan_version': 1,
                'attempt_index': 0, 'specification_version': 1,
                'candidate': 'PRIVATE ANSWER', 'session_key': session,
                'review': {'verdict': 'ACCEPT'}}],
            'calls': {call_id: {'call_id': call_id, 'run_id': 'run',
                'plan_version': 1, 'attempt_index': 0, 'role': 'final_generator',
                'status': 'completed', 'request': request,
                'response': {'final_response': 'PRIVATE ANSWER'}}}}


def step_state():
    report = {'argument': 'PRIVATE ARGUMENT', 'claims': [
        {'statement': r'对任意实数 x，(x-1)^2 >= 0'},
        {'statement': '猜想：全部整数均满足 P(n)'}]}
    verdict = {'valid': True, 'verdict': 'CHALLENGE', 'goal_gate': 'PARTIAL',
               'logic_gate': 'PASS', 'objection': '尚未证明全部整数的情形'}
    state = {'run_id': 'run', 'plan_version': 1, 'attempt_index': 0,
             'specification_version': 1, 'plan': {'steps': [{'step_id': 's1',
             'objective': '验证非负性与整数猜想'}]},
             'steps': {'s1': {'report': report, 'verification': verdict}},
             'calls': {'review': {'call_id': 'review', 'role': 'step_verifier',
                 'status': 'completed', 'run_id': 'run', 'plan_version': 1,
                 'attempt_index': 0, 'request_revision': 5,
                 'request': {'step': {'step_id': 's1', 'objective': '验证非负性与整数猜想'},
                             'report': copy.deepcopy(report)},
                 'response': {**verdict, 'classified_outcomes': [
                     {'category': 'Lemma', 'statement': report['claims'][0]['statement'],
                      'scope': '实数域', 'claim_indexes': [0]},
                     {'category': 'Conjecture', 'statement': report['claims'][1]['statement'],
                      'scope': '全部整数；尚未证明', 'claim_indexes': [1]}]}}}}
    entries, rejected = build_entries(state, state['calls']['review']['response'],
        step_id='s1', report=report, review_call_id='review', suffix='',
        plan_version=1, attempt_index=0)
    assert not rejected
    state['verified_results_ledger'] = entries
    return state, {'type': 'step_reviewed', 'event_id': 'review-event', 'step_id': 's1', **verdict}


class RoleStageReviewsTest(unittest.TestCase):
    def test_classifications_preserve_per_result_scope_under_challenged_step(self):
        state, event = step_state()
        before = copy.deepcopy(state)
        drafts = collect(state, event)
        classified = [d for d in drafts if d['binding'].get('result_id')]
        self.assertEqual(2, len(classified))
        self.assertEqual('accepted', classified[0]['check']['status'])
        self.assertEqual('unreviewed', classified[1]['check']['status'])
        self.assertIn({'label': '阶段结论', 'text': r'对任意实数 x，(x-1)^2 >= 0'}, classified[0]['sections'])
        self.assertIn({'label': '分类', 'text': '猜想'}, classified[1]['sections'])
        self.assertIn({'label': '适用范围', 'text': '全部整数；尚未证明'}, classified[1]['sections'])
        self.assertNotIn('PRIVATE ARGUMENT', json.dumps(drafts))
        self.assertEqual(before, state)
        self.assertEqual(drafts, collect(state, event))
        state['verified_results_ledger'][0]['statement'] = 'changed'
        self.assertIn({'label': '阶段结论', 'text': r'对任意实数 x，(x-1)^2 >= 0'}, classified[0]['sections'])

    def test_whole_review_binds_candidate_and_never_copies_answer_or_reason(self):
        state = {'run_id': 'run', 'plan_version': 1, 'attempt_index': 0,
                 'specification_version': 1, 'calls': {'whole': {
                     'status': 'completed', 'role': 'whole_solution_verifier', 'run_id': 'run',
                     'request': {'solution_candidate': 'PRIVATE CANDIDATE A',
                                 'review_criteria': ['completeness', 'cross_step_logic']},
                     'response': {'verdict': 'ACCEPT', 'reason': 'PRIVATE REASON'}}},
                 'obligation_ledger': [{'status': 'open'}]}
        run = {'run_id': 'run', 'state_revision': 8, 'state': state}
        state['whole_solution_reviews'] = [review_record(run, 'PRIVATE CANDIDATE A',
            'ACCEPT', call_id='whole', origin='final_generator')]
        draft, = collect(state, {'type': 'final_candidate_reviewed', 'event_id': 'e'})
        self.assertEqual('accepted', draft['check']['status'])
        self.assertEqual('整题模型审查通过（仅限所列候选与覆盖目标）', draft['check']['label'])
        self.assertIn({'label': '覆盖目标', 'text': '完整性；跨步骤逻辑'}, draft['sections'])
        self.assertIn({'label': '未解决点', 'text': '仍有 1 项根目标未完成核验。'}, draft['sections'])
        self.assertNotIn('PRIVATE', json.dumps(draft))
        state['calls']['whole']['request']['solution_candidate'] = 'candidate B'
        other, = collect(state, {'type': 'final_candidate_reviewed', 'event_id': 'e2'})
        self.assertEqual('unknown', other['check']['status'])
        self.assertNotEqual(draft['binding'], other['binding'])

    def test_generator_success_and_job_completion_cannot_upgrade_evidence(self):
        state = generator_state()
        draft, = collect(state, {'type': 'final_candidate_generated'})
        self.assertEqual(next(iter(state['calls'])), draft['binding']['generator_call_id'])
        self.assertEqual('unreviewed', draft['check']['status'])
        self.assertNotIn('PRIVATE ANSWER', json.dumps(draft))
        self.assertEqual([], collect(state, {'type': 'finalization_completed'}))
        state['final_solution_attempts'][0]['candidate'] = 'changed'
        self.assertEqual([], collect(state, {'type': 'final_candidate_generated'}))

    def test_generator_resolves_completed_protocol_repair_from_logical_call(self):
        state = generator_state()
        root, = state['calls']
        repaired = copy.deepcopy(state['calls'][root])
        repaired['call_id'] = repaired['request']['call_id'] = root + ':repair-1'
        state['calls'][root]['status'] = 'protocol_failed'
        state['calls'][root]['response'] = None
        state['calls'][root + ':repair-1'] = repaired
        draft, = collect(state, {'type': 'final_candidate_generated'})
        self.assertEqual(root + ':repair-1', draft['binding']['generator_call_id'])
        self.assertEqual('unreviewed', draft['check']['status'])
        repaired['response']['final_response'] = 'different candidate'
        self.assertEqual([], collect(state, {'type': 'final_candidate_generated'}))

    def test_generator_rejects_wrong_sources_even_with_matching_text_and_session(self):
        for field, value in [('call_id', 'unrelated'), ('run_id', 'other'),
                             ('plan_version', 2), ('attempt_index', 1),
                             ('status', 'unknown_outcome'), ('role', 'reasoner')]:
            with self.subTest(field=field):
                state = generator_state()
                root, = state['calls']
                call = state['calls'][root]
                if field == 'call_id':
                    state['calls'] = {value: call}
                    call['call_id'] = call['request']['call_id'] = value
                    call['request']['session_key'] = state['final_solution_attempts'][0]['session_key']
                else:
                    call[field] = value
                self.assertEqual([], collect(state, {'type': 'final_candidate_generated'}))

    def test_generator_does_not_inherit_other_candidate_or_specification_versions(self):
        for target, field, value in [('attempt', 'plan_version', 2),
                                     ('attempt', 'attempt_index', 1),
                                     ('attempt', 'specification_version', 2),
                                     ('attempt', 'invalidated', True),
                                     ('attempt', 'invalidated_by_specification_version', 2),
                                     ('attempt', 'session_key', 'another-candidate'),
                                     ('attempt', 'candidate', 'changed'),
                                     ('request', 'problem_spec_version', 2)]:
            with self.subTest(target=target, field=field):
                state = generator_state()
                record = (state['final_solution_attempts'][0] if target == 'attempt'
                          else next(iter(state['calls'].values()))['request'])
                record[field] = value
                self.assertEqual([], collect(state, {'type': 'final_candidate_generated'}))

    def test_meta_guidance_decision_and_execution_are_distinct_fixed_templates(self):
        state = {'run_id': 'run', 'plan_version': 1, 'attempt_index': 0,
                 'meta_guidance_decision': {'run_id': 'run', 'plan_version': 1,
                     'attempt_index': 0, 'step_id': 's1', 'decided_at_revision': 9,
                     'action_type': 'replan', 'failure_type': 'stuck',
                     'rationale': 'PRIVATE REASON', 'specific_task': 'PRIVATE TASK', 'consumed': None}}
        draft, = collect(state, {'type': 'meta_guidance_decided', 'action_type': 'replan'})
        self.assertIn({'label': '建议', 'text': '建议重新规划，仍需独立决议。'}, draft['sections'])
        self.assertEqual('unreviewed', draft['check']['status'])
        self.assertNotIn('PRIVATE', json.dumps(draft))
        self.assertEqual([], collect(state, {'type': 'plan_archived', 'decision_revision': 9}))
        decision = {**state['meta_guidance_decision'], 'decision': 'APPROVE_REPLAN',
                    'decided_at_revision': 10,
                    'consumed': {'event_type': 'plan_archived', 'state_revision': 12}}
        state['meta_decision'] = decision
        applied, = collect(state, {'type': 'plan_archived', 'decision_revision': 10, 'state_revision': 12})
        self.assertIn({'label': '执行状态', 'text': '已执行：归档旧计划，准备重新规划。'}, applied['sections'])
        self.assertEqual('unreviewed', applied['check']['status'])
        self.assertEqual([], collect(state, {'type': 'plan_archived', 'decision_revision': 9, 'state_revision': 12}))

    def test_finite_computation_keeps_bounded_scope_and_receipt_binding(self):
        state, event = step_state()
        state['tool_receipts'] = [{'receipt_id': 'numeric', 'tool': 'python_math',
            'executed': True, 'status': 'success', 'output': '0,1,4', 'input': 'saved input'}]
        reply = state['calls']['review']['response']
        reply['classified_outcomes'] = [{'category': 'Computation', 'statement': '三个样本的平方非负',
            'scope': '仅 x=0,1,2；不覆盖全体实数', 'receipt_ids': ['numeric']}]
        state['verified_results_ledger'], _ = build_entries(state, reply, step_id='s1',
            report=state['steps']['s1']['report'], review_call_id='review', suffix='',
            plan_version=1, attempt_index=0)
        draft = collect(state, event)[1]
        self.assertEqual('finite_computation', draft['check']['scope'])
        self.assertIn({'label': '适用范围', 'text': '仅 x=0,1,2；不覆盖全体实数'}, draft['sections'])
        self.assertEqual(['numeric'], draft['binding']['receipt_ids'])

    def test_non_authoritative_events_and_wrong_report_do_not_publish(self):
        state, event = step_state()
        self.assertEqual([], collect(state, {'type': 'call_audit', 'role': 'step_verifier'}))
        state['steps']['s1']['report']['claims'][0]['statement'] = 'new report'
        self.assertEqual([], collect(state, event))
        state, event = step_state()
        state['calls']['review']['status'] = 'unknown_outcome'
        self.assertEqual([], collect(state, event))
        state, event = step_state()
        state['attempt_index'] = 1
        self.assertEqual([], collect(state, event))

    def test_local_formal_target_is_not_whole_problem_proof(self):
        target = public_target(normalize_target({'domain': 'rationals', 'variables': ['x'],
            'lhs': '(x+1)**2', 'rhs': 'x**2+2*x+1', 'quantifiers': ['forall x'],
            'assumptions': [], 'direction': 'equality'}))
        current = {'attempt_id': 'formal-a', 'status': 'solved', 'grade': 'L2',
            'specifications': {'original_to_spec': {'problem_spec_version': 1},
                'spec_to_target': {'target_hash': target['hash']},
                'target_to_environment': {'target_hash': target['hash'], 'environment_hash': 'env'}},
            'proof_artifact': {'accepted': True, 'kernel_exit': 0, 'cleanup_verified': True,
                'target_hash': target['hash'], 'environment_hash': 'env',
                'logs': {'stdout': 'PRIVATE LOG'}, 'proof': 'PRIVATE PROOF'}}
        formal = {'policy': {'target': target}, 'current_attempt_id': 'formal-a',
                  'current': current, 'attempts': [current], 'status': 'solved', 'grade': 'L2'}
        state = {'specification_version': 1, 'formal_verification': formal}
        event = {'type': 'formal_verification_completed', 'status': 'solved', 'grade': 'L2'}
        draft, = collect(state, event)
        self.assertEqual('local_formal_target', draft['check']['scope'])
        self.assertEqual('accepted', draft['check']['status'])
        self.assertIn({'label': '形式目标', 'text': '对任意有理数 x，(x+1)**2 = x**2+2*x+1'}, draft['sections'])
        self.assertNotIn('PRIVATE', json.dumps(draft))
        current['proof_artifact']['target_hash'] = 'wrong-target'
        draft, = collect(state, event)
        self.assertEqual('unknown', draft['check']['status'])

    def test_unknown_check_and_sensitive_mathematical_unit_are_not_promoted(self):
        state, event = step_state()
        state['steps']['s1']['verification']['valid'] = False
        event['valid'] = False
        state['verified_results_ledger'] = []
        self.assertEqual('unknown', collect(state, event)[0]['check']['status'])
        state, event = step_state()
        state['verified_results_ledger'][0]['statement'] = 'api_key=private; x>=0'
        self.assertIn({'label': '阶段结论', 'text': '[redacted]'}, collect(state, event)[1]['sections'])

    def test_missing_scope_or_inconsistent_evidence_cannot_claim_check_passed(self):
        state, event = step_state()
        state['verified_results_ledger'][0]['evidence_level'] = 'conjecture'
        self.assertEqual('unknown', collect(state, event)[1]['check']['status'])
        state, event = step_state()
        state['verified_results_ledger'][0]['scope'] = ''
        self.assertEqual('unknown', collect(state, event)[1]['check']['status'])

    def test_meta_actual_decision_remains_strategy_record(self):
        decision = {'decision': 'APPROVE_REPLAN', 'reason_summary': 'PRIVATE REASON',
                    'plan_summary': 'PRIVATE PLAN', 'forbidden_directions': ['PRIVATE'],
                    'reusable_results': [], 'trace_back_to': None}
        state = {'run_id': 'run', 'plan_version': 1, 'attempt_index': 0,
                 'meta_decision': {**decision, 'run_id': 'run', 'plan_version': 1,
                     'attempt_index': 0, 'step_id': 's1', 'decided_at_revision': 12, 'consumed': None}}
        draft, = collect(state, {'type': 'meta_decided', 'decision': decision})
        self.assertIn({'label': '决议', 'text': '批准重新规划'}, draft['sections'])
        self.assertEqual('unreviewed', draft['check']['status'])
        self.assertNotIn('PRIVATE', json.dumps(draft))


if __name__ == '__main__':
    unittest.main()
