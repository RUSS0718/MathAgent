<script setup lang="ts">
import type { DecodedSseEvent } from '../api/events.schemas'

defineProps<{ events: DecodedSseEvent[] }>()

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
</script>

<template>
  <section v-if="events.length" class="agent-timeline" aria-live="polite">
    <header><h2>Agent 执行节点</h2><span>{{ events.length }} 个事件</span></header>
    <ol>
      <li v-for="event in events" :key="`${event.id}-${event.event}`" :class="`event-${event.event}`">
        <div class="timeline-meta"><strong>{{ nodeName(event) }}</strong><span>{{ status(event) }}</span></div>
        <p class="timeline-title">{{ title(event) }}</p>
        <p v-if="summary(event)" class="timeline-summary">{{ summary(event) }}</p>
        <small v-if="event.event === 'tool_call_start' && Array.isArray(event.data.argument_keys)">参数键：{{ event.data.argument_keys.join('、') }}</small>
      </li>
    </ol>
  </section>
</template>
