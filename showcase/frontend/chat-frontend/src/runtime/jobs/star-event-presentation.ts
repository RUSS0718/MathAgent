import type { DecodedSseEvent } from '../../api/events.schemas'

const starEventTitles: Record<string, string> = {
  explore_assessed: 'Explore 路由',
  solution_review_assessed: '整题审查路由',
  partial_exploration_routed: 'Meta 探索决策',
  initial_plan_generated: '计划生成',
  step_reviewed: 'Step Gate',
  challenge_replied: 'Reasoner 回应异议',
  challenge_stalemate: 'Challenge 限次升级',
  challenge_escalation_stopped: 'Challenge 停止',
  meta_dispatched: 'Meta 升级',
  meta_decided: 'Meta 裁定',
  meta_invalid: 'Meta 裁定无效',
  trace_back_applied: '回退与依赖失效',
  plan_archived: '归档旧计划',
  plan_replaced: '执行新计划',
  final_candidate_generated: '生成整题候选',
  final_candidate_reviewed: '最终整题裁决',
  meta_guidance_applied: '执行局部指导',
  best_effort_selected: '选择已有候选',
}

export function solverEventType(event: DecodedSseEvent): string | null {
  if (event.event !== 'solver_progress') return null
  return typeof event.data.solver_event_type === 'string' ? event.data.solver_event_type : 'unknown'
}

export function timelineNodeName(event: DecodedSseEvent): string {
  const solverEvent = solverEventType(event)
  if (solverEvent) return `star:${solverEvent}`
  return typeof event.data.node_name === 'string' ? event.data.node_name : 'system'
}

export function timelineTitle(event: DecodedSseEvent): string {
  const solverEvent = solverEventType(event)
  if (solverEvent) return starEventTitles[solverEvent] ?? 'STAR 状态更新'
  return typeof event.data.title === 'string' ? event.data.title : event.event
}

export function timelineSummary(event: DecodedSseEvent): string {
  const solverEvent = solverEventType(event)
  if (solverEvent) return starSummary(event, solverEvent)
  if (typeof event.data.summary === 'string') return event.data.summary
  if (typeof event.data.message === 'string') return event.data.message
  const data = event.data.data
  if (data && typeof data === 'object' && 'summary' in data) return String(data.summary)
  return ''
}

export function timelineStatus(event: DecodedSseEvent): string {
  const solverEvent = solverEventType(event)
  if (solverEvent) {
    return event.data.valid === false || solverEvent === 'meta_invalid'
      || solverEvent === 'challenge_escalation_stopped' ? 'failed' : 'recorded'
  }
  if (typeof event.data.status === 'string') return event.data.status
  if (event.event === 'node_start') return 'running'
  return event.event
}

export function timelineNodeLabel(node: string): string {
  return node.startsWith('star:') || node === 'star' ? 'STAR' : node
}

export function timelineStatusLabel(value: string): string {
  if (value === 'recorded') return '已记录'
  if (value === 'failed') return '未推进'
  return value
}

export function timelineEventLabel(event: DecodedSseEvent): string {
  return solverEventType(event) ? timelineTitle(event) : event.event
}

function starSummary(event: DecodedSseEvent, solverEvent: string): string {
  if (solverEvent === 'trace_back_applied') return `回退至步骤 ${event.data.trace_back_to ?? '未知'} · 失效 ${event.data.invalidated_result_count ?? '未知'} 项 · 救援 ${event.data.rescued_result_count ?? '未知'} 项`
  if (solverEvent === 'plan_archived' || solverEvent === 'plan_replaced') return `活动计划 v${event.data.plan_version ?? '未知'} · 尝试 ${event.data.attempt_index ?? '未知'}`
  const phaseLabels: Record<string, string> = {
    EXPLORE: '继续探索',
    EXPLORE_REVIEW: '整题审查',
    PLAN: '生成计划',
  }
  if (solverEvent === 'explore_assessed') {
    const assessments: Record<string, string> = {
      SOLVED: '找到完整候选',
      PARTIALLY_SOLVED: '部分解决',
      NEED_PLAN: '需要计划',
      UNKNOWN: '结果未确定',
    }
    const assessment = typeof event.data.assessment === 'string'
      ? assessments[event.data.assessment]
      : undefined
    const destination = typeof event.data.next_phase === 'string'
      ? phaseLabels[event.data.next_phase]
      : undefined
    const round = Number.isSafeInteger(event.data.round) && Number(event.data.round) > 0
      ? `第 ${event.data.round} 轮 `
      : ''
    return assessment && destination
      ? `${round}探索：${assessment} → ${destination}`
      : '探索路由已记录'
  }
  if (solverEvent === 'solution_review_assessed') {
    const verdict = event.data.verdict === 'ACCEPT' || event.data.verdict === 'REJECT'
      ? event.data.verdict
      : null
    const destination = typeof event.data.next_phase === 'string'
      ? phaseLabels[event.data.next_phase]
      : undefined
    return verdict && destination
      ? `整题审查：${verdict} → ${destination}`
      : '整题审查路由已记录'
  }
  if (solverEvent === 'partial_exploration_routed') {
    if (event.data.decision === 'PLAN') return 'Meta 决策：转入计划'
    if (event.data.decision === 'RETRY') return 'Meta 决策：再探索'
    return 'Meta 探索决策已记录'
  }
  if (solverEvent === 'initial_plan_generated') {
    const version = Number.isSafeInteger(event.data.plan_version) && Number(event.data.plan_version) > 0
      ? ` v${event.data.plan_version}`
      : ''
    return `计划${version} 已生成`
  }
  if (solverEvent === 'step_reviewed') {
    const goals = ['YES', 'PARTIAL', 'NO']
    const logic = ['PASS', 'FAIL', 'UNCERTAIN']
    const verdicts = ['ACCEPT', 'CHALLENGE', 'TRACE_BACK', 'PROPOSE_REPLAN']
    const goal = typeof event.data.goal_gate === 'string' && goals.includes(event.data.goal_gate)
      ? event.data.goal_gate
      : null
    const gate = typeof event.data.logic_gate === 'string' && logic.includes(event.data.logic_gate)
      ? event.data.logic_gate
      : null
    const verdict = typeof event.data.verdict === 'string' && verdicts.includes(event.data.verdict)
      ? event.data.verdict
      : null
    if (!goal || !gate || !verdict || typeof event.data.valid !== 'boolean') {
      return '步骤裁决信息不完整'
    }
    const stepId = ordinalStepLabel(event.data.step_id)
    const decision = `${stepId ? `${stepId} · ` : ''}目标 ${goal} · 逻辑 ${gate} · ${verdict} · ${event.data.valid ? '允许推进' : '未允许推进'}`
    if (verdict !== 'CHALLENGE') return decision
    const objection = typeof event.data.objection_summary === 'string'
      ? ` · 异议：${event.data.objection_summary}`
      : ''
    return `${decision}${roleSummary(event)}${usageSummary(event)}${objection}`
  }
  if (solverEvent === 'challenge_replied') {
    const round = validRound(event.data.round)
    const number = round ? `第 ${round} 轮 · ` : ''
    return `${number}${roleLabel(event.data.role)} · 已回应异议${usageSummary(event)}`
  }
  if (solverEvent === 'challenge_stalemate') {
    return `达到质询轮数上限 · ${upgradeReasonLabel(event.data.upgrade_reason)} · 已升级 Meta`
  }
  if (solverEvent === 'meta_dispatched') {
    return `${roleLabel(event.data.role)} 已收到质询升级 · ${upgradeReasonLabel(event.data.upgrade_reason)}`
  }
  if (solverEvent === 'challenge_escalation_stopped') {
    return `Meta 继续后再次遇到异议，已停止 · ${upgradeReasonLabel(event.data.upgrade_reason)}`
  }
  if (solverEvent === 'meta_decided') {
    const decision = typeof event.data.decision === 'string' ? event.data.decision : '未知'
    return `${roleLabel(event.data.role)} 裁定 ${decision} · ${upgradeReasonLabel(event.data.upgrade_reason)}${usageSummary(event)}`
  }
  if (solverEvent === 'meta_invalid') {
    return `${roleLabel(event.data.role)} 裁定无效 · ${upgradeReasonLabel(event.data.upgrade_reason)}`
  }
  return 'STAR 状态已记录'
}

function roleSummary(event: DecodedSseEvent): string {
  return event.data.role ? ` · ${roleLabel(event.data.role)}` : ''
}

function roleLabel(value: unknown): string {
  const labels: Record<string, string> = {
    reasoner: 'Reasoner',
    step_verifier: 'Verifier',
    meta: 'Meta',
    controller: '控制器',
  }
  return typeof value === 'string' ? labels[value] ?? '角色未知' : ''
}

function usageSummary(event: DecodedSseEvent): string {
  const usage = event.data.usage
  if (!usage || typeof usage !== 'object') return ''
  const value = usage as Record<string, unknown>
  const fields: Array<[string, string]> = [
    ['prompt_tokens', '输入'],
    ['completion_tokens', '输出'],
    ['total_tokens', '合计'],
  ]
  const reported = fields.flatMap(([key, label]) =>
    Number.isSafeInteger(value[key]) && Number(value[key]) >= 0
      ? [`${label} ${value[key]}`]
      : [],
  )
  return ` · 用量：${reported.length ? `${reported.join(' · ')} tokens` : '未知'}`
}

function validRound(value: unknown): number | null {
  return Number.isSafeInteger(value) && Number(value) > 0 ? Number(value) : null
}

function upgradeReasonLabel(value: unknown): string {
  if (value === 'round_limit_reached') return '升级原因：轮数上限'
  if (value === 'meta_escalation_limit_reached') return '升级原因：Meta 升级次数上限'
  return '升级原因未知'
}

function ordinalStepLabel(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const match = /^步骤 ([1-9]\d*)$/.exec(value)
  return match && Number.isSafeInteger(Number(match[1])) ? value : null
}
