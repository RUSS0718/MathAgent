<script setup lang="ts">
import AgentTimeline from './AgentTimeline.vue'
import type { JobRecord } from '../stores/jobs.store'
import type { JobReport } from '../api/reports.schemas'
import UiButton from './ui/UiButton.vue'
import UiIcon from './ui/UiIcon.vue'
import StatusBadge from './ui/StatusBadge.vue'
import ResponsivePanel from './ui/ResponsivePanel.vue'

defineProps<{ open: boolean; job?: JobRecord; report: JobReport | null }>()
const emit = defineEmits<{ close: [] }>()

</script>

<template>
  <ResponsivePanel id="inspector-panel" :open="open" :breakpoint="1180" side="right" label="运行观察" @close="emit('close')">
  <aside class="inspector-panel" aria-label="运行观察">
    <div class="inspector-header"><h2>运行观察</h2><UiButton icon-only variant="ghost" aria-label="关闭运行观察" @click="emit('close')"><UiIcon name="close" /></UiButton></div>
    <div v-if="job" class="run-summary"><div class="run-status"><StatusBadge :value="job.status" /><span class="run-id">{{ job.jobId.slice(-8) }}</span></div><div class="run-metrics"><span><b>{{ job.events.length }}</b> 事件</span><span><b>{{ job.lastEventId }}</b> 游标</span></div><a :href="`/dashboard/run/${job.jobId}`">审阅运行与 Evidence</a></div>
    <div v-else class="inspector-empty empty-state"><UiIcon name="activity" /><h3>等待一次运行</h3><p>提交数学题后，这里会显示每个 Agent 节点的状态、工具调用和验证结果。</p></div>
    <AgentTimeline v-if="job" :events="job.events" />
    <section v-if="report" class="inspector-check"><div class="check-heading"><h3>最终验证</h3><StatusBadge :value="report.report.checks?.status ?? 'unknown'" /></div><p>{{ report.report.public_summary }}</p><small>模式：{{ report.mode }} · 阶段：{{ report.report.stage }}</small></section>
    <p v-if="job?.error" class="notice notice--error" role="alert">运行提示：{{ job.error }}</p>
  </aside>
  </ResponsivePanel>
</template>
