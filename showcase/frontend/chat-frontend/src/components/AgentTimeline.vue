<script setup lang="ts">
import { computed, ref } from 'vue'
import type { DecodedSseEvent } from '../api/events.schemas'
import {
  timelineEventLabel,
  timelineNodeLabel,
  timelineNodeName,
  timelineStatus,
  timelineStatusLabel,
  timelineSummary,
  timelineTitle,
} from '../runtime/jobs/star-event-presentation'
import UiIcon from './ui/UiIcon.vue'

const props = defineProps<{ events: DecodedSseEvent[] }>()
const expanded = ref(true)
const expandedSteps = ref<Record<string, boolean>>({})
const roleLabels: Record<string, string> = {
  reasoner: 'Reasoner',
  reason_noncoding: 'Reasoner（非编码）',
  explore: 'Explore',
  explore_polish: 'Explore 整理',
  planner: 'Planner',
  researcher: 'Researcher',
  step_verifier: 'Verifier',
  final_generator: '答案生成',
  whole_solution_verifier: '整题审查',
  meta: 'Meta',
  meta_strategist: 'Meta 策略',
  controller: '控制器',
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
    const key = timelineNodeName(event)
    const current = grouped.get(key) ?? {
      nodeName: key,
      title: timelineTitle(event),
      status: 'running',
      summary: '',
      events: [],
      duration: null,
    }
    current.events.push(event)
    current.title = timelineTitle(event)
    current.status = timelineStatus(event)
    current.summary = timelineSummary(event) || current.summary
    const duration = event.data.duration
    if (typeof duration === 'number') current.duration = duration
    grouped.set(key, current)
  }
  return [...grouped.values()]
})

const roleActivity = computed(() => {
  const counts = new Map<string, number>()
  for (const event of props.events) {
    const role = event.data.role
    if (typeof role === 'string' && role in roleLabels) {
      counts.set(role, (counts.get(role) ?? 0) + 1)
    }
  }
  return [...counts].map(([role, count]) => ({ role, count, label: roleLabels[role] }))
})

function eventCreatedAt(event: DecodedSseEvent): string {
  const value = event.data.created_at
  return typeof value === 'string' && Number.isFinite(Date.parse(value)) ? value : ''
}

function toggleStep(node: string): void {
  expandedSteps.value = { ...expandedSteps.value, [node]: expandedSteps.value[node] === false }
}
</script>

<template>
  <section v-if="events.length" class="agent-timeline" aria-live="polite">
    <section v-if="roleActivity.length" class="timeline-role-view" aria-label="角色活动">
      <h3>角色活动</h3>
      <ul><li v-for="item in roleActivity" :key="item.role">{{ item.label }} · {{ item.count }} 个持久事件</li></ul>
    </section>
    <button class="timeline-header" type="button" :aria-expanded="expanded" @click="expanded = !expanded">
      <span><strong>Agent 执行节点</strong><small>{{ steps.length }} 个节点 · {{ events.length }} 个事件</small></span>
      <UiIcon :name="expanded ? 'chevronDown' : 'chevronRight'" />
    </button>
    <ol v-if="expanded" class="timeline-steps">
      <li v-for="step in steps" :key="step.nodeName" class="timeline-step" :class="`step-${step.status}`">
        <button class="step-header" type="button" :aria-expanded="expandedSteps[step.nodeName] !== false" @click="toggleStep(step.nodeName)">
          <span class="step-status" aria-hidden="true"></span>
          <span class="step-heading"><span class="timeline-title">{{ step.title }}</span><span class="timeline-node">{{ timelineNodeLabel(step.nodeName) }} · {{ step.duration !== null ? `${step.duration}s · ` : '' }}{{ timelineStatusLabel(step.status) }}</span></span>
          <UiIcon :name="expandedSteps[step.nodeName] !== false ? 'chevronDown' : 'chevronRight'" />
        </button>
        <div v-if="expandedSteps[step.nodeName] !== false" class="step-details">
          <p v-if="step.summary && !step.nodeName.startsWith('star:')" class="timeline-summary">{{ step.summary }}</p>
          <ul>
            <li v-for="event in step.events" :key="`${event.id}-${event.event}`" :data-event-id="event.id ?? undefined" :data-event-created-at="eventCreatedAt(event) || undefined">
              <strong>{{ timelineEventLabel(event) }}</strong>
              <span v-if="event.event === 'tool_call_start' && Array.isArray(event.data.argument_keys)">参数键：{{ event.data.argument_keys.join('、') }}</span>
              <span v-else-if="timelineSummary(event) && timelineSummary(event).length <= 240">{{ timelineSummary(event) }}</span>
              <details v-else-if="timelineSummary(event)" class="timeline-long-summary">
                <summary>{{ timelineSummary(event).slice(0, 240) }}… 展开完整摘要</summary>
                <pre>{{ timelineSummary(event) }}</pre>
              </details>
            </li>
          </ul>
        </div>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.timeline-long-summary pre {
  max-height: 24rem;
  overflow: auto;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
</style>
