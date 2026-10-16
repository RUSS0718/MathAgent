<script setup lang="ts">
import { computed } from 'vue'
import { renderSafeMarkdown } from '../renderers/markdown-adapter'
const props = defineProps<{ title?: string; content?: string; mode?: string; report?: { answer: string; public_summary: string; stage: string; limitations: string[] } }>()
const html = computed(() => renderSafeMarkdown(props.content ?? props.report?.answer ?? ''))
</script>
<template><section class="report-section"><h2>{{ title ?? '数学报告' }}</h2><p v-if="mode">模式：{{ mode }}</p><p v-if="report">阶段：{{ report.stage }}</p><div v-html="html"></div><p v-if="report?.public_summary">{{ report.public_summary }}</p><ul v-if="report?.limitations?.length"><li v-for="item in report.limitations" :key="item">{{ item }}</li></ul></section></template>
