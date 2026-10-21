<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import { createIdempotencyKey } from '../runtime/jobs/idempotency'
import { sessionHref, settingsHref, workspaceHref } from '../runtime/navigation/app-route'
import { useJobsStore } from '../stores/jobs.store'
import { useSessionsStore } from '../stores/sessions.store'
import { useFilesStore } from '../stores/files.store'
import ReportSection from './ReportSection.vue'
import { JobController } from '../runtime/jobs/job-controller'
import SessionSidebar from './SessionSidebar.vue'
import MessageList from './MessageList.vue'
import ComposerBar from './ComposerBar.vue'
import WorkspaceInspector from './WorkspaceInspector.vue'

const sessions = useSessionsStore()
const jobs = useJobsStore()
const jobController = new JobController(jobs)
const files = useFilesStore()
const draft = ref('')
const notice = ref('')
const visionEnabled = ref(false)
const executionMode = ref('unavailable')
const selectedFile = ref<string | undefined>()
const selectedFileName = ref<string | undefined>()
const sidebarOpen = ref(false)
const inspectorOpen = ref(true)
const report = ref<Awaited<ReturnType<typeof api.jobReport>> | null>(null)
const props = defineProps<{ path: string; sessionId: string | null }>()
const current = computed(() => sessions.currentId ? jobs.activeForSession(sessions.currentId) : undefined)
const selectedJob = computed(() => {
  const jobId = sessions.messages.at(-1)?.analysis_job_id
  return jobId ? jobs.byId(jobId) : undefined
})

async function send(): Promise<void> {
  const message = draft.value.trim()
  if (!message || current.value || !sessions.currentId) return
  try {
    const result = await api.createJob(message, sessions.currentId, createIdempotencyKey(), selectedFile.value)
    if (!result.success || !result.job_id || !result.status) throw new Error(result.error ?? '任务未被接受')
    jobs.start(result.job_id, sessions.currentId, result.status)
    observeJob(result.job_id)
    sessions.addUser(message, result.job_id)
    draft.value = ''
    selectedFile.value = undefined
    selectedFileName.value = undefined
    await sessions.select(sessions.currentId)
    await loadReport(result.job_id)
  } catch (error) {
    notice.value = error instanceof Error ? error.message : '任务提交失败。'
  }
}
async function cancelCurrent(): Promise<void> {
  if (!current.value) return
  try {
    const result = await api.cancelJob(current.value.jobId, createIdempotencyKey())
    jobs.start(current.value.jobId, current.value.sessionId, result.status ?? 'canceled')
    if (result.status && !['canceled', 'failed', 'succeeded'].includes(result.status)) void jobController.subscribe(current.value.jobId)
    await loadReport(current.value.jobId)
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
    observeJob(current.value.jobId)
    notice.value = result.existing ? '已重放恢复结果。' : '任务已恢复。'
  } catch (error) { notice.value = error instanceof Error ? error.message : '恢复失败。' }
}
async function newSession(): Promise<void> { const id = await sessions.create(); sidebarOpen.value = false; globalThis.history.pushState({}, '', sessionHref(id)); globalThis.dispatchEvent(new PopStateEvent('popstate')) }
async function selectSession(id: string): Promise<void> { await sessions.select(id); sidebarOpen.value = false; globalThis.history.pushState({}, '', sessionHref(id)); globalThis.dispatchEvent(new PopStateEvent('popstate')) }
async function rename(id: string): Promise<void> { const title = globalThis.prompt('会话名称', sessions.items.find((item) => item.id === id)?.preview ?? '新对话'); if (title?.trim()) await sessions.rename(id, title.trim()) }
async function remove(id: string): Promise<void> { await sessions.remove(id); if (!sessions.currentId) globalThis.history.pushState({}, '', workspaceHref()) }
function useStarter(value: string): void { draft.value = value }
function openSettings(): void { globalThis.location.assign(settingsHref()) }
function chooseFile(event: Event): void { const file = (event.target as HTMLInputElement).files?.[0]; if (file) { void files.upload(file).then(() => { selectedFile.value = files.items.at(-1)?.file_id; selectedFileName.value = file.name }) } }
function clearFile(): void { selectedFile.value = undefined; selectedFileName.value = undefined }
async function loadReport(jobId: string): Promise<void> { try { report.value = await api.jobReport(jobId) } catch { report.value = null } }
function observeJob(jobId: string): void {
  void jobController.subscribe(jobId).then(async () => {
    await loadReport(jobId)
    const record = jobs.byId(jobId)
    if (record?.error) notice.value = record.error
  })
}
onMounted(async () => {
  try {
    const capabilities = await api.capabilities()
    executionMode.value = capabilities.execution?.mode ?? 'unavailable'
    if (capabilities.execution?.mode === 'live' && capabilities.execution.status !== 'configured') {
      notice.value = 'live 模式未检测到 Intern API 凭证。'
    }
    visionEnabled.value = capabilities.files.upload.enabled
    if (visionEnabled.value) await files.load()
  } catch (error) {
    notice.value = error instanceof Error ? error.message : '能力检查失败。'
  }
  if (props.path === settingsHref()) return
  if (!sessions.items.length) await sessions.loadList()
  if (props.sessionId) await sessions.select(props.sessionId)
  else if (sessions.currentId) await sessions.select(sessions.currentId)
  else {
    const sessionId = await sessions.create()
    globalThis.history.replaceState({}, '', sessionHref(sessionId))
  }
  const latest = sessions.messages.at(-1)
  if (latest?.analysis_job_id) {
    try {
      jobs.observe(await api.getJob(latest.analysis_job_id))
    } catch (error) {
      notice.value = error instanceof Error ? error.message : '任务状态加载失败。'
    }
    await loadReport(latest.analysis_job_id)
    observeJob(latest.analysis_job_id)
  }
})
</script>

<template>
  <div class="workspace-shell" :class="{ 'sidebar-open': sidebarOpen, 'inspector-open': inspectorOpen }">
    <SessionSidebar :items="sessions.items" :current-id="sessions.currentId" :open="sidebarOpen" @new="newSession" @select="selectSession" @rename="rename" @remove="remove" @settings="openSettings" @close="sidebarOpen = false" />
    <main>
      <div class="workspace-topbar"><button class="icon-button mobile-only" type="button" aria-label="打开会话栏" @click="sidebarOpen = true">☰</button><div class="topbar-title"><span class="topbar-kicker">MATHAGENT</span><strong>{{ sessions.items.find((item) => item.id === sessions.currentId)?.preview ?? '新数学会话' }}</strong></div><div class="topbar-actions"><span class="live-pill" :class="{ 'is-fake': executionMode === 'fake' }"><i></i>{{ (report?.mode ?? executionMode).toUpperCase() }}</span><button class="inspector-toggle" type="button" :aria-pressed="inspectorOpen" @click="inspectorOpen = !inspectorOpen">{{ inspectorOpen ? '隐藏运行观察' : '显示运行观察' }}</button></div></div>
      <p v-if="notice" class="workspace-notice" role="status">{{ notice }}</p>
      <section class="conversation-area"><div class="conversation-scroll"><MessageList :messages="sessions.messages" @starter="useStarter" /><ReportSection v-if="report" :mode="report.mode" :status="report.status" :report="report.report" /></div><ComposerBar v-model="draft" :disabled="Boolean(current)" :running="Boolean(current && !['succeeded','failed','canceled'].includes(current.status))" :vision-enabled="visionEnabled" :selected-file-name="selectedFileName" @submit="send" @cancel="cancelCurrent" @upload="chooseFile" @clear-file="clearFile" /></section>
    </main>
    <WorkspaceInspector :open="inspectorOpen" :job="selectedJob" :report="report" @close="inspectorOpen = false" />
  </div>
</template>

