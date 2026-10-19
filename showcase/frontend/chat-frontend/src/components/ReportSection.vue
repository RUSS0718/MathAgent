<script setup lang="ts">
import { computed } from 'vue'
import { renderSafeMarkdown } from '../renderers/markdown-adapter'
const props = defineProps<{ title?: string; content?: string; mode?: string; status?: string; report?: { answer: string; public_summary: string; stage: string; limitations: string[]; checks?: { status?: string; findings?: string[] } } }>()
const html = computed(() => renderSafeMarkdown(props.content ?? props.report?.answer ?? ''))
const labels = {
  mode: { live: '实时', fake: '演示', replay: '回放', unavailable: '不可用', experimental: '实验', planned: '计划中' },
  status: { succeeded: '已完成', failed: '失败', canceled: '已取消', queued: '排队中', running: '运行中', waiting_input: '等待补充', needs_review: '需要复核' },
  stage: { terminal: '已完成', completed: '已完成', failed: '失败', synthesizing: '整理答案', verifying: '验证中', solving: '求解中', planning: '规划中' },
  check: { pass: '通过', conflict: '存在冲突', unknown: '未知' },
} as const
function translate(group: keyof typeof labels, value?: string): string {
  if (!value) return ''
  return labels[group][value as keyof (typeof labels)[typeof group]] ?? value
}
</script>
<template><section class="report-section"><h2>{{ title ?? '数学报告' }}</h2><div class="report-meta"><span v-if="mode">模式：{{ translate('mode', mode) }}</span><span v-if="status">状态：{{ translate('status', status) }}</span><span v-if="report">阶段：{{ translate('stage', report.stage) }}</span><span v-if="report?.checks?.status">校验：{{ translate('check', report.checks.status) }}</span></div><div v-if="html" class="report-content" v-html="html"></div><p v-if="report?.public_summary" class="report-summary">{{ report.public_summary }}</p><ul v-if="report?.limitations?.length" class="report-limitations"><li v-for="item in report.limitations" :key="item">{{ item }}</li></ul></section></template>
