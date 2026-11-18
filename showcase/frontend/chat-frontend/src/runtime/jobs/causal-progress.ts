import type { DecodedSseEvent } from '../../api/events.schemas.ts'

export const statusLabels: Record<string, string> = {
  queued: '等待开始', running: '正在处理', waiting_input: '等待补充条件', succeeded: '执行完成',
  completed: '执行结束', failed: '执行遇到问题', canceled: '任务已取消', unknown: '结果未知', needs_review: '需要人工复核',
  idle: '未参与', pass: '步骤检查通过', active: '执行中', pending: '等待执行', challenged: '发现问题', revised: '已撤回',
  ended_unconfirmed: '任务已结束，步骤结果未确认', historical_active: '历史记录：执行中（结果未确认）', historical_pending: '历史记录：等待执行',
}
export const roleLabels: Record<string, string> = {
  controller: '任务协调', explore: '问题探索', explore_polish: '探索整理', planner: '方案规划', reasoner: '推理',
  reason_noncoding: '推理', researcher: '资料研究', step_verifier: '步骤检查', whole_solution_verifier: '答案审查',
  final_generator: '答案整理', meta: '策略调整', meta_strategist: '策略调整', unknown: '角色待确认',
}
const keyTitles: Record<string, string> = {
  adaptive_planning_required: '求解安排已更新', adaptive_candidate_correction: '答案需要修正',
  initial_plan_generated: '求解计划已形成', plan_replaced: '已调整求解方案', step_reported: '步骤结果已提交',
  step_reviewed: '步骤检查已完成', challenge_replied: '已回应步骤疑问', challenge_stalemate: '正在调整处理策略',
  challenge_escalation_stopped: '步骤问题尚未解决', meta_dispatched: '正在评估调整方案', meta_decided: '调整方案已形成',
  meta_invalid: '调整方案尚未通过', trace_back_applied: '已回退重新推理', final_candidate_generated: '候选答案已整理',
  final_candidate_reviewed: '答案审查已完成', finalization_completed: '本轮成果已保存',
  explore_assessed: '问题探索已完成', solution_review_assessed: '答案审查结论已记录',
  final_result: '执行完成，请查看答案和实际检查结论', interrupt: '等待补充条件', error: '执行遇到问题',
  canceled: '任务已取消', timeout: '执行超时', needs_review: '需要人工复核',
}
export const typeOf = (event: DecodedSseEvent) => String(event.data.solver_event_type ?? event.event)
export function eventRole(event: DecodedSseEvent): string {
  const role = event.data.role
  const aliases: Record<string, string> = { reason_noncoding: 'reasoner', explore_polish: 'explore', meta_strategist: 'meta' }
  return typeof role === 'string' && Object.hasOwn(roleLabels, role) ? Object.hasOwn(aliases, role) ? aliases[role]! : role : 'unknown'
}
function callLifecycle(event: DecodedSseEvent): unknown { return event.data.call_lifecycle ?? event.data.call_status }
export function progressText(event: DecodedSseEvent) {
  const type = typeOf(event)
  const callProblem = type === 'call_audit' && ['failed', 'unknown'].includes(String(callLifecycle(event)))
  const critical = callProblem || ['waiting_input', 'failed', 'canceled', 'unknown', 'needs_review'].includes(String(event.data.status))
  const title = critical ? statusLabels[String(callProblem ? callLifecycle(event) : event.data.status)]! : Object.hasOwn(keyTitles, type) ? keyTitles[type]! : '技术记录'
  const verdict = event.data.verdict ?? (event.data.review as Record<string, unknown> | undefined)?.verdict
  const routeSummaries = ['题目中的目标有先后依赖，先制定分步方案。',
    '本次探索达到输出上限，转入制定方案。', '本次探索未完成，转入制定方案。',
    '已形成完整候选，交由独立答案审查。', '探索表明需要分步处理，转入制定方案。',
    '已取得部分进展，转入分步求解。', '本次探索尚不能形成完整答案，转入制定方案。',
    '已取得部分进展，继续探索。']
  const route = ['adaptive_planning_required', 'explore_assessed'].includes(type)
    && typeof event.data.routing_summary === 'string' && routeSummaries.includes(event.data.routing_summary)
    ? event.data.routing_summary : null
  const summary = !critical && route ? route : type === 'step_reviewed' || type === 'final_candidate_reviewed'
    ? verdict === 'ACCEPT' ? '本次检查通过；检查范围见结果，不等于形式化证明。'
      : verdict === 'CHALLENGE' || verdict === 'REJECT' ? '检查发现问题，尚未通过。' : '检查结论待确认。'
    : critical ? '请查看任务状态及可用操作；结果未知时不要重复提交。' : title
  return { title, summary, key: critical || Object.hasOwn(keyTitles, type) }
}
export function lifecycle(events: DecodedSseEvent[], replay: boolean, status: string) {
  const calls = new Map<string, { role: string; status: string; startedAt?: string }>()
  const states: Record<string, string> = Object.fromEntries(Object.keys(roleLabels).map(role => [role, 'idle']))
  for (const event of events) {
    const role = eventRole(event)
    if (role === 'unknown') continue
    const id = event.data.solver_call_id
    const state = callLifecycle(event)
    if (typeof id === 'string' && typeof state === 'string' && ['running', 'completed', 'failed', 'unknown'].includes(state)) {
      calls.set(id, { role, status: state, startedAt: calls.get(id)?.startedAt ?? (typeof event.data.created_at === 'string' ? event.data.created_at : undefined) })
    } else if (event.event === 'node_start') calls.set(`${role}:${event.data.step_id}`, { role, status: 'running' })
    else if (event.event === 'node_end') calls.set(`${role}:${event.data.step_id}`, { role, status: event.data.status === 'failed' ? 'failed' : 'completed' })
    else if (progressText(event).key && !['meta_dispatched', 'adaptive_planning_required', 'adaptive_candidate_correction'].includes(typeOf(event))) states[role] = event.data.status === 'failed'
      || typeOf(event) === 'meta_invalid' ? 'failed' : event.data.status === 'unknown' || event.data.status === 'needs_review' ? 'unknown' : 'completed'
  }
  for (const role of Object.keys(states)) {
    const owned = [...calls.values()].filter(call => call.role === role).map(call => call.status)
    if (owned.length) states[role] = owned.includes('running') ? 'running' : owned.includes('unknown') ? 'unknown'
      : owned.includes('failed') ? 'failed' : 'completed'
    if (states[role] === 'running' && (replay || status && status !== 'running' && status !== 'queued')) states[role] = 'unknown'
  }
  const activeTimes = [...calls.values()].filter(call => call.status === 'running' && states[call.role] === 'running')
    .map(call => Date.parse(call.startedAt ?? '')).filter(Number.isFinite)
  return { states, startedAt: activeTimes.length ? Math.min(...activeTimes) : null }
}
