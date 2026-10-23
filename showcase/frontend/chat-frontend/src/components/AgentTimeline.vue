<script setup lang="ts">
import { computed, ref } from 'vue'
import type { DecodedSseEvent } from '../api/events.schemas'
import UiIcon from './ui/UiIcon.vue'

const props = defineProps<{ events: DecodedSseEvent[] }>()
const expanded = ref(true)
const expandedSteps = ref<Record<string, boolean>>({})

const starEventTitles: Record<string, string> = {
  explore_assessed: 'Explore 路由',
  solution_review_assessed: '整题审查路由',
  partial_exploration_routed: 'Meta 探索决策',
  initial_plan_generated: '计划生成',
  step_reviewed: 'Step Gate',
}

interface TimelineStep {
  nodeName: string
  title: string
  status: string
  summary: string
  events: DecodedSseEvent[]
  duration: number | null
}

const steps = computed<TimelineStep[]>(() => {
  const grouped = new Map<string, TimelineStep>()
  for (const event of props.events) {
    const key = nodeName(event)
    const current = grouped.get(key) ?? {
      nodeName: key,
      title: title(event),
      status: 'running',
      summary: '',
      events: [],
      duration: null,
    }
    current.events.push(event)
    current.title = title(event)
    current.status = status(event)
    current.summary = summary(event) || current.summary
    const duration = event.data.duration
    if (typeof duration === 'number') current.duration = duration
    grouped.set(key, current)
  }
  return [...grouped.values()]
})

function nodeName(event: DecodedSseEvent): string {
  const solverEvent = solverEventType(event)
  if (solverEvent) return `star:${solverEvent}`
  return typeof event.data.node_name === 'string' ? event.data.node_name : 'system'
}

function title(event: DecodedSseEvent): string {
  const solverEvent = solverEventType(event)
  if (solverEvent) return starEventTitles[solverEvent] ?? 'STAR 状态更新'
  return typeof event.data.title === 'string' ? event.data.title : event.event
}

function summary(event: DecodedSseEvent): string {
  const solverEvent = solverEventType(event)
  if (solverEvent) return starSummary(event, solverEvent)
  if (typeof event.data.summary === 'string') return event.data.summary
  if (typeof event.data.message === 'string') return event.data.message
  const data = event.data.data
  if (data && typeof data === 'object' && 'summary' in data) return String(data.summary)
  return ''
}

function status(event: DecodedSseEvent): string {
  if (solverEventType(event)) return event.data.valid === false ? 'failed' : 'recorded'
  if (typeof event.data.status === 'string') return event.data.status
  if (event.event === 'node_start') return 'running'
  return event.event
}

function solverEventType(event: DecodedSseEvent): string | null {
  if (event.event !== 'solver_progress') return null
  return typeof event.data.solver_event_type === 'string' ? event.data.solver_event_type : 'unknown'
}

function starSummary(event: DecodedSseEvent, solverEvent: string): string {
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
    const stepId = typeof event.data.step_id === 'string' && event.data.step_id.trim()
      ? `步骤 ${event.data.step_id.trim()} · `
      : ''
    return `${stepId}目标 ${goal} · 逻辑 ${gate} · ${verdict} · ${event.data.valid ? '允许推进' : '未允许推进'}`
  }
  return 'STAR 状态已记录'
}

function nodeLabel(node: string): string {
  return node.startsWith('star:') || node === 'star' ? 'STAR' : node
}

function statusLabel(value: string): string {
  if (value === 'recorded') return '已记录'
  if (value === 'failed') return '未推进'
  return value
}

function eventLabel(event: DecodedSseEvent): string {
  return solverEventType(event) ? title(event) : event.event
}

function toggleStep(node: string): void {
  expandedSteps.value = { ...expandedSteps.value, [node]: expandedSteps.value[node] === false }
}
</script>

<template>
  <section v-if="events.length" class="agent-timeline" aria-live="polite">
    <button class="timeline-header" type="button" :aria-expanded="expanded" @click="expanded = !expanded">
      <span><strong>Agent 执行节点</strong><small>{{ steps.length }} 个节点 · {{ events.length }} 个事件</small></span>
      <UiIcon :name="expanded ? 'chevronDown' : 'chevronRight'" />
    </button>
    <ol v-if="expanded" class="timeline-steps">
      <li v-for="step in steps" :key="step.nodeName" class="timeline-step" :class="`step-${step.status}`">
        <button class="step-header" type="button" :aria-expanded="expandedSteps[step.nodeName] !== false" @click="toggleStep(step.nodeName)">
          <span class="step-status" aria-hidden="true"></span>
          <span class="step-heading"><span class="timeline-title">{{ step.title }}</span><span class="timeline-node">{{ nodeLabel(step.nodeName) }} · {{ step.duration !== null ? `${step.duration}s · ` : '' }}{{ statusLabel(step.status) }}</span></span>
          <UiIcon :name="expandedSteps[step.nodeName] !== false ? 'chevronDown' : 'chevronRight'" />
        </button>
        <div v-if="expandedSteps[step.nodeName] !== false" class="step-details">
          <p v-if="step.summary && !step.nodeName.startsWith('star:')" class="timeline-summary">{{ step.summary }}</p>
          <ul>
            <li v-for="event in step.events" :key="`${event.id}-${event.event}`">
              <strong>{{ eventLabel(event) }}</strong>
              <span v-if="event.event === 'tool_call_start' && Array.isArray(event.data.argument_keys)">参数键：{{ event.data.argument_keys.join('、') }}</span>
              <span v-else-if="summary(event)">{{ summary(event) }}</span>
            </li>
          </ul>
        </div>
      </li>
    </ol>
  </section>
</template>
