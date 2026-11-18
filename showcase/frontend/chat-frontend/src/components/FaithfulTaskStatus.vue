<script setup lang="ts">
import { computed } from 'vue'
import type { FaithfulTaskState } from '../api/jobs.schemas'
import UiButton from './ui/UiButton.vue'
const props = defineProps<{ state: FaithfulTaskState; busy?: boolean; clarification?: boolean }>()
const emit = defineEmits<{ pause: []; resume: []; cancel: []; refresh: [] }>()
const labels: Record<string, string> = {
  clarification: '需要澄清', waiting_input: '等待输入', converging: '正在收敛',
  pause_requested: '已请求暂停，等待安全步骤边界', paused: '已暂停',
  unknown: '结果未知，请查看运行详情核对', failed: '执行失败', protocol_error: '协议错误，执行失败',
  budget_exhausted: '预算耗尽，任务未完成', incomplete: '任务未完成',
  completed: '任务完成', canceled: '任务已取消，未完成', queued: '等待执行', running: '正在执行', intake: '正在理解题目',
}
const label = computed(() => props.clarification ? '需要澄清：请补充下方条件' : labels[props.state.phase] ?? `正在执行：${props.state.phase}`)
</script>

<template>
  <section class="faithful-task-status notice" aria-label="Faithful 任务状态">
    <p role="status" aria-live="polite">{{ label }}</p>
    <p v-if="state.reason" class="muted">{{ state.reason }}</p>
    <p v-if="state.phase === 'paused'">请到运行详情使用父 Run 专用恢复控制。</p>
    <div class="action-row">
      <UiButton v-if="state.allowed_actions.includes('pause')" :disabled="busy" @click="emit('pause')">请求安全暂停</UiButton>
      <UiButton v-if="!clarification && state.phase !== 'paused' && state.allowed_actions.includes('resume')" :disabled="busy" @click="emit('resume')">恢复执行</UiButton>
      <UiButton v-if="!clarification && state.allowed_actions.includes('cancel')" :disabled="busy" @click="emit('cancel')">取消任务</UiButton>
      <UiButton v-if="['unknown', 'pause_requested'].includes(state.phase)" :disabled="busy" @click="emit('refresh')">刷新任务状态</UiButton>
    </div>
  </section>
</template>

<style scoped>
.faithful-task-status { min-width: 0; overflow-wrap: anywhere; }
.action-row { display: flex; flex-wrap: wrap; gap: var(--space-2); }
</style>
