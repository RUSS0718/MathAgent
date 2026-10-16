<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import { createIdempotencyKey } from '../runtime/jobs/idempotency'
import { sessionHref, settingsHref, workspaceHref } from '../runtime/navigation/app-route'
import { useJobsStore } from '../stores/jobs.store'
import { useSessionsStore } from '../stores/sessions.store'
import ReportSection from './ReportSection.vue'

const sessions = useSessionsStore()
const jobs = useJobsStore()
const draft = ref('')
const notice = ref('')
const report = ref<Awaited<ReturnType<typeof api.jobReport>> | null>(null)
const props = defineProps<{ path: string; sessionId: string | null }>()
const current = computed(() => sessions.currentId ? jobs.activeForSession(sessions.currentId) : undefined)

async function send(): Promise<void> {
  const message = draft.value.trim()
  if (!message || current.value || !sessions.currentId) return
  const result = await api.createJob(message, sessions.currentId, createIdempotencyKey())
  if (!result.success || !result.job_id || !result.status) throw new Error(result.error ?? '任务未被接受')
  jobs.start(result.job_id, sessions.currentId, result.status)
  sessions.addUser(message, result.job_id)
  draft.value = ''
  await sessions.select(sessions.currentId)
  await loadReport(result.job_id)
}
async function cancelCurrent(): Promise<void> {
  if (!current.value) return
  try {
    const result = await api.cancelJob(current.value.jobId, createIdempotencyKey())
    jobs.start(current.value.jobId, current.value.sessionId, result.status ?? 'canceled')
    notice.value = result.existing ? '已重放取消结果。' : '任务已取消。'
  } catch (error) { notice.value = error instanceof Error ? error.message : '取消失败。' }
}
async function resumeCurrent(): Promise<void> {
  if (!current.value) return
  const answer = globalThis.prompt('补充条件', '')
  if (answer === null) return
  try {
    const result = await api.resumeJob(current.value.jobId, answer, createIdempotencyKey())
    jobs.start(current.value.jobId, current.value.sessionId, result.status ?? 'queued')
    notice.value = result.existing ? '已重放恢复结果。' : '任务已恢复。'
  } catch (error) { notice.value = error instanceof Error ? error.message : '恢复失败。' }
}
async function newSession(): Promise<void> { const id = await sessions.create(); globalThis.history.pushState({}, '', sessionHref(id)); globalThis.dispatchEvent(new PopStateEvent('popstate')) }
async function selectSession(id: string): Promise<void> { await sessions.select(id); globalThis.history.pushState({}, '', sessionHref(id)); globalThis.dispatchEvent(new PopStateEvent('popstate')) }
async function rename(id: string): Promise<void> { const title = globalThis.prompt('会话名称', sessions.items.find((item) => item.id === id)?.preview ?? '新对话'); if (title?.trim()) await sessions.rename(id, title.trim()) }
async function remove(id: string): Promise<void> { await sessions.remove(id); if (!sessions.currentId) globalThis.history.pushState({}, '', workspaceHref()) }
async function loadReport(jobId: string): Promise<void> { try { report.value = await api.jobReport(jobId) } catch { report.value = null } }
onMounted(async () => { if (props.path === settingsHref()) return; if (!sessions.items.length) await sessions.loadList(); if (props.sessionId) await sessions.select(props.sessionId); else if (sessions.currentId) await sessions.select(sessions.currentId); const latest = sessions.messages.at(-1); if (latest?.analysis_job_id) await loadReport(latest.analysis_job_id) })
</script>

<template>
  <div class="workspace">
    <aside class="sidebar">
      <header><strong>MathAgent</strong><button type="button" @click="newSession">新建会话</button></header>
      <ul><li v-for="item in sessions.items" :key="item.id" :class="{ selected: item.id === sessions.currentId }"><button type="button" @click="selectSession(item.id)">{{ item.preview }}</button><button type="button" @click="rename(item.id)" aria-label="重命名">✎</button><button type="button" @click="remove(item.id)" aria-label="删除">×</button></li></ul>
      <a :href="settingsHref()">设置</a>
    </aside>
    <main>
      <h1>数学工作区</h1>
      <p v-if="notice" role="status">{{ notice }}</p>
      <section class="messages" aria-live="polite"><article v-for="(message, index) in sessions.messages" :key="`${message.analysis_job_id}-${index}`" :class="message.sender"><strong>{{ message.sender === 'user' ? '你' : 'MathAgent' }}</strong><p>{{ message.text }}</p></article><p v-if="!sessions.messages.length">输入一道数学题开始。</p></section>
      <ReportSection v-if="report" :mode="report.mode" :report="report.report" />
      <p v-if="current">任务状态：{{ current.status }} <button type="button" @click="cancelCurrent" :disabled="['succeeded','failed','canceled'].includes(current.status)">取消</button><button v-if="current.status === 'waiting_input'" type="button" @click="resumeCurrent">恢复</button></p>
      <form @submit.prevent="send"><textarea v-model="draft" aria-label="数学问题" placeholder="输入数学问题" :disabled="Boolean(current)"></textarea><button type="submit" :disabled="!draft.trim() || Boolean(current)">提交</button></form>
    </main>
  </div>
</template>
