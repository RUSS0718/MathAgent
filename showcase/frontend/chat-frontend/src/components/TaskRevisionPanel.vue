<script setup lang="ts">
import { computed, ref } from 'vue'
import { taskRevisionStateSchema } from '../api/jobs.schemas'
import { readSubmission, submitOnce } from '../runtime/jobs/submission'
import ComposerBar from './ComposerBar.vue'

const props = defineProps<{
  jobId: string; sessionId: string; owner: string; mode: string
  state: unknown; disabled: boolean; readonly?: boolean
}>()
const emit = defineEmits<{ changed: [jobId: string, nextJobId: string] }>()
const state = computed(() => taskRevisionStateSchema.safeParse(props.state).data)
const saved = readSubmission(props.owner, props.sessionId)?.input
const restored = saved?.revision?.taskId === props.jobId ? saved : null
const draft = ref(restored?.message ?? '')
const pending = ref(false)
const error = ref('')

async function revise(): Promise<void> {
  if (!draft.value.trim() || !state.value?.revision_allowed || pending.value) return
  pending.value = true
  error.value = ''
  try {
    const result = await submitOnce(props.owner, restored ? { ...restored, message: draft.value.trim() } : {
      sessionId: props.sessionId, message: draft.value.trim(), mode: props.mode,
      revision: { taskId: props.jobId, inputVersion: state.value.input_version },
    })
    if (!result.success || !result.job_id) throw new Error('改题未被接受，请重试同一输入。')
    emit('changed', props.jobId, result.job_id)
  } catch (failure) {
    error.value = `${failure instanceof Error ? failure.message : '改题失败。'} 提交身份已保留，重试同一输入会核对原任务。`
  } finally { pending.value = false }
}
</script>

<template>
  <section v-if="state" class="task-revision" aria-label="关联任务与改题">
    <nav aria-label="关联任务">
      <a v-if="state.revision_source" :href="`/dashboard/run/${state.revision_source.task_id}`">查看原任务</a>
      <a v-if="state.revision_to" :href="`/dashboard/run/${state.revision_to.task_id}`">查看改题后的任务</a>
    </nav>
    <template v-if="state.revision_allowed && !readonly">
      <h2>改题或追加要求</h2>
      <p>请输入包含新要求的完整题目。提交后原任务停止后续派发；已发出的远端请求可能仍在执行并按原任务结算。回答上方的澄清问题请使用“补充条件”。</p>
      <ComposerBar v-model="draft" submit-label="改题并创建新任务" :disabled="disabled || pending" :busy="pending" :running="false" :vision-enabled="false" @submit="revise" />
    </template>
    <p v-if="state.revision_to" role="status">已创建关联新任务。原任务不再派发新工作，在途或未知请求仍保留原身份与预留。</p>
    <p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>

<style scoped>
.task-revision { margin-block: var(--space-4); overflow-wrap: anywhere; }
nav { display: flex; flex-wrap: wrap; gap: var(--space-3); }
h2 { margin-block: var(--space-4) var(--space-2); font-size: var(--text-lg); }
p { margin-block: var(--space-2); }
</style>
