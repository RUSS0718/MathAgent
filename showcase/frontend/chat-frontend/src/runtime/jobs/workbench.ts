import type { DecodedSseEvent } from '../../api/events.schemas.ts'
import { collaborationSchema, evidenceChainSchema } from '../../api/workbench.schemas.ts'
import { timelineSummary, timelineTitle } from './star-event-presentation.ts'

export const roles = [
  ['controller', '中枢', 500, 306], ['explore', '探索', 234, 175],
  ['planner', '规划', 500, 90], ['reasoner', '推理', 766, 175],
  ['step_verifier', '步骤校验', 831, 365], ['whole_solution_verifier', '整体校验', 648, 518],
  ['final_generator', '终稿生成', 352, 518], ['meta', '元策略', 169, 365],
] as const
export interface PlanStep { label: string; status: string }
export function object(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

/** Pure projection shared by every view, without launching work or scheduling scenes. */
export function projectWorkbench(events: DecodedSseEvent[], result: unknown, replay: boolean) {
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
  const steps: PlanStep[] = Array.isArray(progress.steps) ? progress.steps.map(value => {
    const step = object(value)
    return { label: String(step.label ?? '步骤'), status: step.verdict === 'CHALLENGE' ? 'challenged'
      : step.verdict === 'ACCEPT' && step.valid === true ? 'pass' : step.current === true ? 'active'
        : !step.reported && revised.has(String(step.label)) ? 'revised' : 'pending' }
  }) : []
  const entries = unique.map(event => {
    const parsed = collaborationSchema.safeParse(event.data.workbench)
    const message = parsed.success ? parsed.data : null
    const evidence = evidenceChainSchema.safeParse(event.data.evidence_chain)
    const type = String(event.data.solver_event_type ?? '')
    const inferred = type.startsWith('meta_') ? 'meta' : type === 'step_reported' ? 'reasoner'
      : type === 'initial_plan_generated' ? 'planner' : type === 'explore_assessed' ? 'explore'
      : type === 'step_reviewed' ? 'step_verifier' : 'controller'
    const role = typeof event.data.role === 'string' ? event.data.role : inferred
    return { event, role, step: message?.step_label ?? (typeof event.data.step_id === 'string' && /^步骤 \d+$/.test(event.data.step_id) ? event.data.step_id : ''),
      title: timelineTitle(event), summary: message?.kind === 'challenge' && typeof event.data.objection_summary === 'string'
        ? `${message.summary}：${event.data.objection_summary}` : message?.summary ?? timelineSummary(event), message,
      evidence: evidence.success ? evidence.data : [] }
  })
  const source = detail.execution_mode === 'fake' ? 'FAKE · 模拟数据'
    : evidenceKind === 'scripted' || evidenceKind === 'fault_injection' ? 'FAKE · 受控数据'
    : replay ? 'REPLAY · 历史重放' : detail.execution_mode === 'live' || evidenceKind === 'live' ? 'LIVE · 实时' : 'UNKNOWN · 来源待确认'
  return { events: unique, entries, steps, progress, source }
}
