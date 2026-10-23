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
          <span class="step-heading"><span class="timeline-title">{{ step.title }}</span><span class="timeline-node">{{ timelineNodeLabel(step.nodeName) }} · {{ step.duration !== null ? `${step.duration}s · ` : '' }}{{ timelineStatusLabel(step.status) }}</span></span>
          <UiIcon :name="expandedSteps[step.nodeName] !== false ? 'chevronDown' : 'chevronRight'" />
        </button>
        <div v-if="expandedSteps[step.nodeName] !== false" class="step-details">
          <p v-if="step.summary && !step.nodeName.startsWith('star:')" class="timeline-summary">{{ step.summary }}</p>
          <ul>
            <li v-for="event in step.events" :key="`${event.id}-${event.event}`">
              <strong>{{ timelineEventLabel(event) }}</strong>
              <span v-if="event.event === 'tool_call_start' && Array.isArray(event.data.argument_keys)">参数键：{{ event.data.argument_keys.join('、') }}</span>
              <span v-else-if="timelineSummary(event)">{{ timelineSummary(event) }}</span>
            </li>
          </ul>
        </div>
      </li>
    </ol>
  </section>
</template>
