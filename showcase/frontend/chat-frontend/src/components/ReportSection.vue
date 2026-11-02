<script setup lang="ts">
import { computed } from 'vue'
import { renderSafeMarkdown } from '../renderers/markdown-adapter'
import StatusBadge from './ui/StatusBadge.vue'
import type { ResultSemantics } from '../api/result-semantics.schemas'
import { describeResultSemantics } from '../runtime/reports/result-semantics'
const props = defineProps<{ title?: string; content?: string; mode?: string; status?: string; report?: { answer: string; public_summary: string; stage: string; limitations: string[]; checks?: { status?: string; findings?: string[]; history?: Record<string, unknown>[] }; semantics?: ResultSemantics | null } }>()
const html = computed(() => renderSafeMarkdown(props.content ?? props.report?.answer ?? ''))
const labels = {
  stage: { terminal: '执行结束', completed: '已完成', failed: '失败', synthesizing: '整理答案', verifying: '验证中', solving: '求解中', planning: '规划中' },
} as const
function translate(group: keyof typeof labels, value?: string): string {
  if (!value) return ''
  return labels[group][value as keyof (typeof labels)[typeof group]] ?? value
}
</script>
<template>
  <section class="report-section">
    <h2>{{ title ?? '数学报告' }}</h2>
    <div class="report-meta"><StatusBadge v-if="mode" :value="mode" /><StatusBadge v-if="status" :value="status" /><span v-if="report">阶段：{{ translate('stage', report.stage) }}</span><StatusBadge v-if="!report?.semantics && report?.checks?.status" :value="report.checks.status" /></div>
    <p v-if="report?.semantics" class="report-summary" aria-label="结果语义">{{ describeResultSemantics(report.semantics) }}</p>
    <div v-if="html" class="report-content" v-html="html"></div>
    <p v-if="report?.public_summary" class="report-summary">{{ report.public_summary }}</p>
    <details v-if="report?.checks?.history?.length">
      <summary>验证历史（{{ report.checks.history.length }} 项）</summary>
      <p>整题 LLM 审查和局部检查分别保留；均不等于形式化证明。</p>
      <details v-for="(observation, index) in report.checks.history" :key="index">
        <summary>检查 {{ index + 1 }} · {{ observation.scope }}</summary>
        <dl class="data-list"><template v-for="(value, field) in observation" :key="field"><dt>{{ field }}</dt><dd>{{ typeof value === 'object' ? JSON.stringify(value) : String(value) }}</dd></template></dl>
      </details>
    </details>
    <ul v-if="report?.limitations?.length" class="report-limitations"><li v-for="item in report.limitations" :key="item">{{ item }}</li></ul>
  </section>
</template>
