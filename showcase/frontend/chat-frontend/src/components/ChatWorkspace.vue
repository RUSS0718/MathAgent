<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import { createIdempotencyKey } from '../runtime/jobs/idempotency'
import { sessionHref, settingsHref, workspaceHref } from '../runtime/navigation/app-route'
import { useJobsStore } from '../stores/jobs.store'
import { useSessionsStore } from '../stores/sessions.store'

const sessions = useSessionsStore()
const jobs = useJobsStore()
const draft = ref('')
const notice = ref('')
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
}
async function newSession(): Promise<void> { const id = await sessions.create(); globalThis.history.pushState({}, '', sessionHref(id)); globalThis.dispatchEvent(new PopStateEvent('popstate')) }
async function selectSession(id: string): Promise<void> { await sessions.select(id); globalThis.history.pushState({}, '', sessionHref(id)); globalThis.dispatchEvent(new PopStateEvent('popstate')) }
async function rename(id: string): Promise<void> { const title = globalThis.prompt('会话名称', sessions.items.find((item) => item.id === id)?.preview ?? '新对话'); if (title?.trim()) await sessions.rename(id, title.trim()) }
async function remove(id: string): Promise<void> { await sessions.remove(id); if (!sessions.currentId) globalThis.history.pushState({}, '', workspaceHref()) }
onMounted(async () => { if (props.path === settingsHref()) return; if (!sessions.items.length) await sessions.loadList(); if (props.sessionId) await sessions.select(props.sessionId); else if (sessions.currentId) await sessions.select(sessions.currentId) })
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
      <form @submit.prevent="send"><textarea v-model="draft" aria-label="数学问题" placeholder="输入数学问题" :disabled="Boolean(current)"></textarea><button type="submit" :disabled="!draft.trim() || Boolean(current)">提交</button></form>
    </main>
  </div>
</template>
