<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
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
import StarModeSelector from './StarModeSelector.vue'
import WorkspaceInspector from './WorkspaceInspector.vue'
import UiButton from './ui/UiButton.vue'
import UiIcon from './ui/UiIcon.vue'
import StatusBadge from './ui/StatusBadge.vue'

const sessions = useSessionsStore()
const jobs = useJobsStore()
const jobController = new JobController(jobs)
const files = useFilesStore()
const draft = ref('')
const notice = ref('')
const visionEnabled = ref(false)
const executionMode = ref('unavailable')
const solverMode = ref('legacy')
const solverModes = ref<Array<{ solver_mode: string; enabled: boolean }>>([])
const selectedFile = ref<string | undefined>()
const selectedFileName = ref<string | undefined>()
const sidebarOpen = ref(false)
const inspectorOpen = ref(!globalThis.matchMedia('(max-width: 1180px)').matches)
const submitting = ref(false)
const loading = ref(true)
const loadFailed = ref(false)
const report = ref<Awaited<ReturnType<typeof api.jobReport>> | null>(null)
const props = defineProps<{ path: string; sessionId: string | null }>()
const current = computed(() => sessions.currentId ? jobs.activeForSession(sessions.currentId) : undefined)
const selectedJob = computed(() => {
  const jobId = sessions.messages.at(-1)?.analysis_job_id
  return jobId ? jobs.byId(jobId) : undefined
})

async function send(): Promise<void> {
  if (current.value?.status === 'waiting_input') { await resumeCurrent(); return }
  const message = draft.value.trim()
  if (!message || current.value || !sessions.currentId || submitting.value) return
  submitting.value = true
  notice.value = ''
  try {
    const result = await api.createJob(message, sessions.currentId, createIdempotencyKey(), selectedFile.value, solverMode.value)
    if (!result.success || !result.job_id || !result.status) throw new Error(result.error ?? '任务未被接受')
    jobs.start(result.job_id, sessions.currentId, result.status)
    observeJob(result.job_id)
    sessions.addUser(message, result.job_id)
    report.value = null
    draft.value = ''
    selectedFile.value = undefined
    selectedFileName.value = undefined
    await sessions.select(sessions.currentId)
    await loadReport(result.job_id)
  } catch (error) {
    notice.value = error instanceof Error ? error.message : '任务提交失败。'
  } finally { submitting.value = false }
}
async function cancelCurrent(): Promise<void> {
  const target = current.value
  if (!target) return
  try {
    const result = await api.cancelJob(target.jobId, createIdempotencyKey())
    jobs.start(target.jobId, target.sessionId, result.status ?? 'canceled')
    if (result.status && !['canceled', 'failed', 'succeeded'].includes(result.status)) void jobController.subscribe(target.jobId)
    await loadReport(target.jobId)
    notice.value = result.existing ? '已重放取消结果。' : '任务已取消。'
  } catch (error) { notice.value = error instanceof Error ? error.message : '取消失败。' }
}
async function resumeCurrent(): Promise<void> {
  if (!current.value || !draft.value.trim() || submitting.value) return
  const answer = draft.value.trim()
  submitting.value = true
  try {
    const result = await api.resumeJob(current.value.jobId, answer, createIdempotencyKey())
    jobs.start(current.value.jobId, current.value.sessionId, result.status ?? 'queued')
    observeJob(current.value.jobId)
    draft.value = ''
    notice.value = result.existing ? '已重放恢复结果。' : '任务已恢复。'
  } catch (error) { notice.value = error instanceof Error ? error.message : '恢复失败。' }
  finally { submitting.value = false }
}
async function sessionAction(action: () => Promise<void>): Promise<void> { try { await action() } catch (error) { notice.value = error instanceof Error ? error.message : '会话操作失败，请重试。' } }
async function newSession(): Promise<void> { await sessionAction(async () => { const id = await sessions.create(); sidebarOpen.value = false; globalThis.history.pushState({}, '', sessionHref(id)); globalThis.dispatchEvent(new PopStateEvent('popstate')) }) }
async function selectSession(id: string): Promise<void> { await sessionAction(async () => { await sessions.select(id); sidebarOpen.value = false; globalThis.history.pushState({}, '', sessionHref(id)); globalThis.dispatchEvent(new PopStateEvent('popstate')) }) }
async function rename(id: string): Promise<void> { const title = globalThis.prompt('会话名称', sessions.items.find((item) => item.id === id)?.preview ?? '新对话'); if (title?.trim()) await sessionAction(() => sessions.rename(id, title.trim())) }
async function remove(id: string): Promise<void> { if (!globalThis.confirm('删除此会话？此操作无法撤销。')) return; await sessionAction(async () => { await sessions.remove(id); if (!sessions.currentId) { globalThis.history.pushState({}, '', workspaceHref()); globalThis.dispatchEvent(new PopStateEvent('popstate')) } }) }
function useStarter(value: string): void { draft.value = value; document.getElementById('math-question')?.focus() }
function openSettings(): void { globalThis.location.assign(settingsHref()) }
async function chooseFile(event: Event): Promise<void> { const input = event.target as HTMLInputElement; const file = input.files?.[0]; if (!file) return; try { await files.upload(file); selectedFile.value = files.items.at(-1)?.file_id; selectedFileName.value = file.name } catch (error) { notice.value = error instanceof Error ? error.message : '题图上传失败，请重试。' } finally { input.value = '' } }
function clearFile(): void { selectedFile.value = undefined; selectedFileName.value = undefined }
async function loadReport(jobId: string): Promise<void> { try { report.value = await api.jobReport(jobId) } catch { report.value = null } }
function observeJob(jobId: string): void {
  void jobController.subscribe(jobId).then(async () => {
    await loadReport(jobId)
    const record = jobs.byId(jobId)
    if (record?.error) notice.value = record.error
  })
}
async function initialize(): Promise<void> {
  loading.value = true
  loadFailed.value = false
  notice.value = ''
  try {
  try {
    const capabilities = await api.capabilities()
    executionMode.value = capabilities.execution?.mode ?? 'unavailable'
    if (capabilities.execution?.mode === 'live' && capabilities.execution.status !== 'configured') {
      notice.value = 'live 模式未检测到 Intern API 凭证。'
    }
    solverModes.value = capabilities.solver_modes ?? []
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
  } catch (error) { loadFailed.value = true; notice.value = error instanceof Error ? error.message : '会话加载失败，请重试。' }
  finally { loading.value = false }
}
onMounted(initialize)
onUnmounted(() => jobController.stopAll())
</script>

<template>
  <div class="workspace-shell" :class="{ 'sidebar-open': sidebarOpen, 'inspector-open': inspectorOpen }">
    <a class="skip-link" href="#main-content">跳到主要内容</a>
    <SessionSidebar :items="sessions.items" :current-id="sessions.currentId" :open="sidebarOpen" @new="newSession" @select="selectSession" @rename="rename" @remove="remove" @settings="openSettings" @close="sidebarOpen = false" />
    <main id="main-content" tabindex="-1">
      <header class="workspace-topbar">
        <UiButton icon-only variant="ghost" class="mobile-only" aria-label="打开会话栏" aria-controls="session-panel" :aria-expanded="sidebarOpen" @click="sidebarOpen = true"><UiIcon name="menu" /></UiButton>
        <div class="topbar-title"><h1>{{ sessions.items.find((item) => item.id === sessions.currentId)?.preview ?? '新数学会话' }}</h1></div>
        <div class="topbar-actions"><StatusBadge :value="report?.mode ?? executionMode" /><UiButton icon-only variant="ghost" :aria-label="inspectorOpen ? '隐藏运行观察' : '显示运行观察'" :title="inspectorOpen ? '隐藏运行观察' : '显示运行观察'" aria-controls="inspector-panel" :aria-expanded="inspectorOpen" @click="inspectorOpen = !inspectorOpen"><UiIcon name="panel" /></UiButton></div>
      </header>
      <div v-if="notice" class="notice workspace-notice" role="status">{{ notice }}<UiButton v-if="loadFailed" @click="initialize">重新加载</UiButton></div>
      <div v-if="current?.status === 'waiting_input'" class="notice notice--warning workspace-notice" role="status">运行需要补充条件，请在输入栏填写后继续。</div>
      <section class="conversation-area" aria-label="数学对话">
        <div class="conversation-scroll"><div v-if="loading" class="loading-state" role="status" aria-busy="true">正在加载会话…<div v-for="n in 3" :key="n" class="skeleton"></div></div><MessageList v-else-if="!loadFailed" :messages="sessions.messages" @starter="useStarter" /><ReportSection v-if="report" :mode="report.mode" :status="report.status" :report="report.report" /></div>
        <ComposerBar v-model="draft" :disabled="loading || loadFailed || submitting || Boolean(current && current.status !== 'waiting_input')" :running="Boolean(current)" :waiting="current?.status === 'waiting_input'" :vision-enabled="visionEnabled" :selected-file-name="selectedFileName" @submit="send" @cancel="cancelCurrent" @upload="chooseFile" @clear-file="clearFile"><template #mode><StarModeSelector v-model="solverMode" :modes="solverModes" :disabled="Boolean(current) || submitting" /></template></ComposerBar>
      </section>
    </main>
    <WorkspaceInspector :open="inspectorOpen" :job="selectedJob" :report="report" @close="inspectorOpen = false" />
  </div>
</template>
