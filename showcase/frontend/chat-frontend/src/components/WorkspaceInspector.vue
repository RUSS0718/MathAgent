<script setup lang="ts">
import AgentTimeline from './AgentTimeline.vue'
import type { JobRecord } from '../stores/jobs.store'
import type { JobReport } from '../api/reports.schemas'

defineProps<{ open: boolean; job?: JobRecord; report: JobReport | null }>()
const emit = defineEmits<{ close: [] }>()

const statusLabels: Record<string, string> = { queued: '排队中', running: '运行中', waiting_input: '等待输入', succeeded: '已完成', failed: '需要复核', canceled: '已取消' }
function statusLabel(value?: string): string { return value ? statusLabels[value] ?? value : '等待任务' }
</script>

<template>
  <aside class="inspector-panel" :class="{ 'is-open': open }">
    <div class="inspector-header"><div><p class="eyebrow">RUN OBSERVER</p><h2>运行观察</h2></div><button class="icon-button" type="button" aria-label="关闭运行观察" @click="emit('close')">×</button></div>
    <div v-if="job" class="run-summary"><div class="run-status"><span class="status-pulse" :class="`status-${job.status}`"></span><strong>{{ statusLabel(job.status) }}</strong><span>{{ job.jobId.slice(-8) }}</span></div><div class="run-metrics"><span><b>{{ job.events.length }}</b> 事件</span><span><b>{{ job.lastEventId }}</b> 游标</span></div></div>
    <div v-else class="inspector-empty"><span class="empty-icon" aria-hidden="true">◌</span><strong>等待一次运行</strong><p>提交数学题后，这里会显示每个 Agent 节点的状态、工具调用和验证结果。</p></div>
    <AgentTimeline v-if="job" :events="job.events" />
    <section v-if="report" class="inspector-check"><div class="check-heading"><span>最终验证</span><strong>{{ report.report.checks?.status === 'pass' ? '通过' : report.report.checks?.status === 'unknown' ? '待确认' : '需复核' }}</strong></div><p>{{ report.report.public_summary }}</p><small>模式：{{ report.mode }} · 阶段：{{ report.report.stage }}</small></section>
    <section v-if="job?.error" class="inspector-error"><strong>运行提示</strong><p>{{ job.error }}</p></section>
  </aside>
</template>
