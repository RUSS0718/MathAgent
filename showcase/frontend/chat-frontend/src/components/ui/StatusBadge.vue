<script setup lang="ts">
/** A raw value remains visible so an unknown backend state cannot look successful. */
import { computed } from 'vue'
const props = defineProps<{ value: string }>()
const labels: Record<string, string> = { star_limited: 'STAR 受限', fake: '演示', replay: '回放', live: '实时', experimental: '实验', unavailable: '不可用', planned: '计划中', queued: '排队中', running: '运行中', waiting_input: '等待补充', succeeded: '已完成', completed: '已终止', failed: '失败', canceled: '已取消', pass: '检查通过', unknown: '未知', conflict: '存在冲突' }
const tone = computed(() => ['succeeded', 'pass', 'live'].includes(props.value) ? 'success' : ['failed', 'conflict'].includes(props.value) ? 'danger' : ['fake', 'replay', 'experimental', 'waiting_input', 'running', 'queued'].includes(props.value) ? 'warning' : 'neutral')
</script>

<template><span class="status-badge" :class="`status-badge--${tone}`"><span class="status-dot" aria-hidden="true"></span><span class="status-label">{{ labels[value] ?? value }}</span><span v-if="labels[value]" class="status-code">{{ value }}</span></span></template>
