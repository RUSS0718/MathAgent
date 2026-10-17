<script setup lang="ts">
import { computed, ref } from 'vue'
import type { DecodedSseEvent } from '../api/events.schemas'

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
  return typeof event.data.node_name === 'string' ? event.data.node_name : 'system'
}

function title(event: DecodedSseEvent): string {
  return typeof event.data.title === 'string' ? event.data.title : event.event
}

function summary(event: DecodedSseEvent): string {
  if (typeof event.data.summary === 'string') return event.data.summary
  if (typeof event.data.message === 'string') return event.data.message
  const data = event.data.data
  if (data && typeof data === 'object' && 'summary' in data) return String(data.summary)
  return ''
}

function status(event: DecodedSseEvent): string {
  if (typeof event.data.status === 'string') return event.data.status
  if (event.event === 'node_start') return 'running'
  return event.event
}

function toggleStep(node: string): void {
  expandedSteps.value = { ...expandedSteps.value, [node]: !expandedSteps.value[node] }
}
</script>

<template>
  <section v-if="events.length" class="agent-timeline" aria-live="polite">
    <button class="timeline-header" type="button" :aria-expanded="expanded" @click="expanded = !expanded">
      <span><strong>Agent 执行节点</strong><small>{{ steps.length }} 个节点 · {{ events.length }} 个事件</small></span>
      <span aria-hidden="true">{{ expanded ? '▾' : '▸' }}</span>
    </button>
    <ol v-if="expanded" class="timeline-steps">
      <li v-for="step in steps" :key="step.nodeName" class="timeline-step" :class="`step-${step.status}`">
        <button class="step-header" type="button" :aria-expanded="expandedSteps[step.nodeName] !== false" @click="toggleStep(step.nodeName)">
          <span class="step-status" aria-hidden="true"></span>
          <span class="timeline-title">{{ step.title }}</span>
          <span class="timeline-node">{{ step.nodeName }}</span>
          <span class="timeline-duration">{{ step.duration !== null ? `${step.duration}s` : step.status }}</span>
          <span aria-hidden="true">{{ expandedSteps[step.nodeName] !== false ? '▾' : '▸' }}</span>
        </button>
        <div v-if="expandedSteps[step.nodeName] !== false" class="step-details">
          <p v-if="step.summary" class="timeline-summary">{{ step.summary }}</p>
          <ul>
            <li v-for="event in step.events" :key="`${event.id}-${event.event}`">
              <span>{{ event.event }}</span>
              <span v-if="event.event === 'tool_call_start' && Array.isArray(event.data.argument_keys)">参数键：{{ event.data.argument_keys.join('、') }}</span>
              <span v-else-if="summary(event)">{{ summary(event) }}</span>
            </li>
          </ul>
        </div>
      </li>
    </ol>
  </section>
</template>
