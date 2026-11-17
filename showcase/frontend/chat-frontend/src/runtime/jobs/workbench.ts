import type { DecodedSseEvent } from '../../api/events.schemas.ts'
import { collaborationSchema, evidenceChainSchema } from '../../api/workbench.schemas.ts'
import { timelineSummary, timelineTitle } from './star-event-presentation.ts'
import { eventRole, lifecycle, progressText, roleLabels, statusLabels, typeOf } from './causal-progress.ts'

export const roles = [
  ['controller', '任务协调', 500, 306], ['explore', '问题探索', 234, 175],
  ['planner', '规划', 500, 90], ['reasoner', '推理', 766, 175],
  ['step_verifier', '步骤校验', 831, 365], ['whole_solution_verifier', '整体校验', 648, 518],
  ['final_generator', '终稿生成', 352, 518], ['meta', '元策略', 169, 365],
  ['researcher', '资料研究', 500, 610],
] as const
export interface PlanStep { label: string; status: string; goal: string }
export function object(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

/** Pure projection shared by every view, without launching work or scheduling scenes. */
export function projectWorkbench(events: DecodedSseEvent[], result: unknown, replay: boolean, status = '') {
  const seen = new Set<number>()
  const unique = events.filter(event => event.id !== null && event.event !== 'heartbeat'
    && !seen.has(event.id) && Boolean(seen.add(event.id)))
  const detail = object(result)
  let progress: Record<string, unknown> = {}
  let revision = 0
  let evidenceKind: unknown = detail.evidence_kind
  for (const event of unique) {
    const snapshot = object(object(event.data.solver).progress)
    if (Array.isArray(snapshot.steps)) {
      progress = snapshot
      revision = Number(event.data.solver_revision ?? 0)
    }
    evidenceKind = event.data.evidence_kind ?? evidenceKind
  }
  const latest = object(object(detail.solver).progress)
  if (Array.isArray(latest.steps) && Number(object(detail.solver).state_revision ?? 0) >= revision) progress = latest
  const revised = new Set<string>()
  for (const event of unique) {
    const message = collaborationSchema.safeParse(event.data.workbench)
    if (message.success && message.data.plan_version === progress.plan_version) {
      for (const change of message.data.changes ?? []) if (change.op === 'del') revised.add(change.step_label)
    }
  }
  const planEnded = ['failed', 'canceled', 'cancelled', 'succeeded', 'completed', 'partial', 'incomplete', 'budget_exhausted'].includes(status)
  const planUncertain = ['unknown', 'needs_review', 'unknown_outcome'].includes(status)
    || ['unknown', 'needs_review'].includes(String(object(detail.faithful).phase))
  const activeStepStatus = replay ? 'historical_active' : planEnded ? 'ended_unconfirmed' : planUncertain ? 'unknown' : 'active'
  const pendingStepStatus = replay || planEnded ? 'historical_pending' : 'pending'
  const steps: PlanStep[] = Array.isArray(progress.steps) ? progress.steps.map(value => {
    const step = object(value)
    return { label: String(step.label ?? '步骤'), goal: typeof step.goal_summary === 'string' ? step.goal_summary : '', status: step.verdict === 'CHALLENGE' ? 'challenged'
      : step.verdict === 'ACCEPT' && step.valid === true ? 'pass' : step.current === true ? activeStepStatus
        : !step.reported && revised.has(String(step.label)) ? 'revised' : pendingStepStatus }
  }) : []
  const entries = unique.map(event => {
    const parsed = collaborationSchema.safeParse(event.data.workbench)
    const message = parsed.success ? parsed.data : null
    const evidence = evidenceChainSchema.safeParse(event.data.evidence_chain)
    const type = String(event.data.solver_event_type ?? '')
    const role = eventRole(event)
    return { event, role, step: message?.step_label ?? (typeof event.data.step_id === 'string' && /^步骤 \d+$/.test(event.data.step_id) ? event.data.step_id : ''),
      title: timelineTitle(event), summary: typeof event.data.role_stage_source === 'string' && typeof event.data.role_stage_summary === 'string'
        ? event.data.role_stage_summary : message?.kind === 'challenge' && typeof event.data.objection_summary === 'string'
        ? `${message.summary}：${event.data.objection_summary}` : message?.summary ?? timelineSummary(event), message,
      evidence: evidence.success ? evidence.data : [] }
  })
  const source = detail.execution_mode === 'fake' ? 'FAKE · 模拟数据'
    : evidenceKind === 'scripted' || evidenceKind === 'fault_injection' ? 'FAKE · 受控数据'
    : replay ? 'REPLAY · 历史重放' : detail.execution_mode === 'live' || evidenceKind === 'live' ? 'LIVE · 实时' : 'UNKNOWN · 来源待确认'
  const saved = object(progress.partial)
  const partial = {
    accepted: Array.isArray(saved.accepted_steps) ? saved.accepted_steps.map(String) : [],
    unresolved: Array.isArray(saved.unresolved) ? saved.unresolved.map(String) : [],
    candidates: Array.isArray(saved.candidates) ? saved.candidates.map(value => {
      const candidate = object(value)
      return { text: String(candidate.answer_text ?? ''), review: String(candidate.review ?? 'UNREVIEWED'), eligible: candidate.eligible === true }
    }) : [],
  }
  const semantic = new Set<string>()
  const keyEntries = entries.filter(entry => {
    if (!progressText(entry.event).key) return false
    const data = entry.event.data
    const key = JSON.stringify([typeOf(entry.event), data.role_stage_source, data.plan_version ?? entry.message?.plan_version,
      data.attempt_index ?? entry.message?.attempt_index, entry.step, data.verdict, data.valid,
      progressText(entry.event).summary, data.status, data.call_lifecycle ?? data.call_status, data.solver_call_id, data.decision, entry.message?.thread_id, entry.message?.kind, entry.message?.summary])
    if (semantic.has(key)) return false
    semantic.add(key)
    return true
  }).map(entry => {
    const progress = progressText(entry.event)
    const savedSummary = typeof entry.event.data.role_stage_source === 'string'
      && typeof entry.event.data.role_stage_summary === 'string'
    return { ...entry, ...progress, summary: savedSummary ? entry.summary : progress.summary }
  })
  const taskPhase = object(detail.faithful).phase
  const effectiveStatus = ['unknown', 'needs_review', 'waiting_input', 'paused', 'pause_requested', 'budget_exhausted', 'incomplete'].includes(String(taskPhase)) ? String(taskPhase) : status
  const activity = lifecycle(unique, replay, effectiveStatus)
  const roleStates = activity.states
  const running = Object.keys(roleStates).filter(role => roleStates[role] === 'running')
  const terminal = effectiveStatus && !['running', 'queued'].includes(effectiveStatus)
  const lastKey = keyEntries.at(-1)
  const phaseLabels: Record<string, string> = { INTAKE: '正在理解题目', EXPLORE: '正在探索问题', PLAN: '正在制定方案',
    STEP_EXECUTE: '正在分步推理', STEP_REVIEW: '正在检查步骤', TRACE_BACK: '正在回退修正',
    EXECUTE: '正在分步推理', FINAL: '正在整理答案', FINALIZE: '正在整理答案', EXPLORE_REVIEW: '正在审查答案', TERMINAL: '执行结束' }
  const solver = unique.reduce((latest, event) => {
    const snapshot = object(event.data.solver)
    return Object.keys(snapshot).length && Number(snapshot.state_revision ?? event.data.solver_revision ?? 0) >= Number(latest.state_revision ?? 0) ? snapshot : latest
  }, object(detail.solver))
  const phase = terminal ? statusLabels[effectiveStatus] ?? '请查看任务状态及允许的操作'
    : running.length ? running.map(role => `${roleLabels[role]}中`).join('、')
      : phaseLabels[String(solver.phase)] ?? lastKey?.title ?? statusLabels[status] ?? '等待公开阶段信息'
  const phaseStartedAt = activity.startedAt
  return { events: unique, entries, keyEntries, roleStates, phase, phaseStartedAt, steps, progress, source, partial }
}
