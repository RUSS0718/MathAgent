<script setup lang="ts">
import { ref } from 'vue'
import { api } from '../api/client'
import { isApiError } from '../api/errors'
import type { ClarificationState } from '../api/jobs.schemas'
import { createIdempotencyKey } from '../runtime/jobs/idempotency'
import UiButton from './ui/UiButton.vue'

const props = defineProps<{ state: ClarificationState; resuming: boolean }>()
const emit = defineEmits<{
  changed: [jobId: string, nextJobId?: string]
  cancel: []
  resume: []
}>()
const answer = ref('')
const pending = ref(false)
const error = ref('')
let sent: { answer: string; key: string } | undefined

async function submit(): Promise<void> {
  if (pending.value || !answer.value.trim()) return
  const question = props.state.clarification
  const text = answer.value.trim()
  if (sent?.answer !== text) sent = { answer: text, key: createIdempotencyKey() }
  pending.value = true
  error.value = ''
  try {
    await api.answerClarification(question.task_id, question.request_id, question.input_version, text, sent.key)
    emit('changed', question.task_id)
  } catch (failure) {
    if (isApiError(failure) && failure.code === 'clarification_expired') {
      emit('changed', question.task_id)
    } else {
      error.value = isApiError(failure) && failure.status === 409
        ? '澄清请求或回答已变化。请查看当前任务状态。'
        : '无法确认回答是否收到。回答已保留，可以重试。'
      emit('changed', question.task_id)
    }
  } finally { pending.value = false }
}

async function newTask(): Promise<void> {
  if (pending.value) return
  const question = props.state.clarification
  pending.value = true
  error.value = ''
  try {
    const storageKey = `mathagent:clarification:new-task:${question.request_id}`
    const key = sessionStorage.getItem(storageKey) ?? createIdempotencyKey()
    sessionStorage.setItem(storageKey, key)
    const result = await api.newTaskFromClarification(question.task_id, question.request_id, key)
    if (!result.job_id) throw new Error('missing job identity')
    emit('changed', question.task_id, result.job_id)
  } catch {
    error.value = '暂时无法确认新任务。请重试或刷新查看会话。'
  } finally { pending.value = false }
}
</script>

<template>
  <section class="clarification-panel" aria-labelledby="clarification-heading">
    <h2 id="clarification-heading">{{ state.clarification.status === 'answered' ? '已补充条件' : state.clarification.status === 'evaluating' ? '已收到回答，待判断条件是否充分' : '需要补充条件' }}</h2>
    <p>{{ state.clarification.question }}</p>
    <p v-if="state.clarification.status === 'waiting'">{{ state.clarification.reason }}</p>
    <p v-if="state.clarification.answer">你的回答：{{ state.clarification.answer }}</p>
    <p v-if="state.clarification.status === 'expired'" role="status">原任务已到期，回答已保存。你可以带着补充条件开始关联新任务。</p>
    <p v-if="state.allowed_actions.includes('save_clarification')" role="status">原任务已到期，可以保存回答后开始关联新任务。</p>
    <form v-if="state.allowed_actions.some(action => ['answer_clarification', 'save_clarification'].includes(action))" @submit.prevent="submit">
      <label for="clarification-answer">补充条件</label>
      <textarea id="clarification-answer" v-model="answer" rows="3" maxlength="8000" required :disabled="pending" />
      <div class="clarification-actions">
        <UiButton type="submit" variant="primary" :busy="pending" :disabled="!answer.trim()">{{ state.allowed_actions.includes('save_clarification') ? '保存回答' : '回答并继续' }}</UiButton>
        <UiButton v-if="state.allowed_actions.includes('cancel')" :disabled="pending" @click="emit('cancel')">取消任务</UiButton>
      </div>
    </form>
    <UiButton v-if="state.allowed_actions.includes('create_new_task')" variant="primary" :busy="pending" @click="newTask">带着回答开始新任务</UiButton>
    <UiButton v-if="state.allowed_actions.includes('resume')" variant="primary" :busy="resuming" @click="emit('resume')">恢复执行</UiButton>
    <p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>

<style scoped>
.clarification-panel { margin-block: var(--space-4); padding: var(--space-4); border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface); overflow-wrap: anywhere; }
h2 { margin: 0; font-size: 1rem; }
form { display: grid; gap: var(--space-2); }
textarea { width: 100%; padding: var(--space-2); color: var(--text); background: var(--background); border: 1px solid var(--border-strong); border-radius: var(--radius-md); font: inherit; resize: vertical; }
.clarification-actions { display: flex; flex-wrap: wrap; gap: var(--space-2); }
</style>
