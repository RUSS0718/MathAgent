<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api/client'
import type { CapabilitiesResponse } from '../api/capabilities.schemas'
import { clarificationStateSchema } from '../api/jobs.schemas'
import { lookupSubmission, readSubmission, submitOnce } from '../runtime/jobs/submission'
import { useAuthStore } from '../stores/auth.store'
import { createIdempotencyKey } from '../runtime/jobs/idempotency'
import { sessionHref, settingsHref, workspaceHref } from '../runtime/navigation/app-route'
import { useJobsStore } from '../stores/jobs.store'
import { useSessionsStore } from '../stores/sessions.store'
import { useFilesStore } from '../stores/files.store'
import ReportSection from './ReportSection.vue'
import PresentationSection from './PresentationSection.vue'
import { JobController } from '../runtime/jobs/job-controller'
import { parsePresentationInput } from '../runtime/presentation/mode'
import type { PresentationMode } from '../runtime/presentation/mode'
import SessionSidebar from './SessionSidebar.vue'
import ComposerBar from './ComposerBar.vue'
import StarModeSelector from './StarModeSelector.vue'
import FaithfulEntryControls from './FaithfulEntryControls.vue'
import PresentationCommandHint from './PresentationCommandHint.vue'
import UiButton from './ui/UiButton.vue'
import UiIcon from './ui/UiIcon.vue'
import ConversationWorkbench from './ConversationWorkbench.vue'
import ClarificationPanel from './ClarificationPanel.vue'
import TaskRevisionPanel from './TaskRevisionPanel.vue'

const auth = useAuthStore()
const sessions = useSessionsStore()
const jobs = useJobsStore()
const jobController = new JobController(jobs)
const files = useFilesStore()
const draft = ref('')
const notice = ref('')
const visionEnabled = ref(false)
const presentationEnabled = ref(false)
const solverMode = ref('legacy')
const faithful = ref<CapabilitiesResponse['faithful']>()
const faithfulBlocked = computed(() => faithful.value?.enabled === true && !faithful.value.ready)
const autonomous = computed(() => faithful.value?.enabled === true && solverMode.value === faithful.value.solver_mode)
const solverModes = ref<Array<{ solver_mode: string; enabled: boolean }>>([])
const selectedFile = ref<string | undefined>()
const selectedFileName = ref<string | undefined>()
const sidebarOpen = ref(false)
const submitting = ref(false)
const checkingSubmission = ref(false)
const loading = ref(true)
const loadFailed = ref(false)
const report = ref<Awaited<ReturnType<typeof api.jobReport>> | null>(null)
let reportDisposed = false
const props = defineProps<{ path: string; sessionId: string | null }>()
const current = computed(() => sessions.currentId ? jobs.activeForSession(sessions.currentId) : undefined)
const selectedJob = computed(() => {
  if (current.value) return current.value
  const jobId = sessions.messages.at(-1)?.analysis_job_id
  return jobId ? jobs.byId(jobId) : undefined
})
const presentationMode = computed(() => selectedJob.value?.presentationMode ?? null)
const clarification = computed(() => clarificationStateSchema.safeParse(selectedJob.value?.result?.faithful).data)
const showReport = computed(() => !clarification.value ||
  (clarification.value.clarification.status === 'answered' && !current.value) ? report.value : null)
const selectedProblem = computed(() => {
  const jobId = selectedJob.value?.jobId
  return [...sessions.messages].reverse().find((message) => message.analysis_job_id === jobId && message.sender === 'user')?.text ?? ''
})
const workbenchResult = computed(() => ({ ...selectedJob.value?.result,
  ...(report.value?.mode === 'fake' ? { execution_mode: 'fake' } : {}) }))

async function send(): Promise<void> {
  if (loading.value || loadFailed.value || faithfulBlocked.value) return
  if (current.value?.status === 'waiting_input') { notice.value = '文本插话尚未接入；请使用恢复执行按钮。'; return }
  const parsed = parsePresentationInput(draft.value)
  const message = parsed.problem
  if (parsed.presentationMode && !presentationEnabled.value) {
    notice.value = 'S06 输出模式当前不可用；原题未提交。'
    return
  }
  if (!message || current.value || !sessions.currentId || submitting.value) {
    if (!message && parsed.presentationMode) notice.value = '请在输出命令后输入数学题目，例如：/teach 证明 1+1=2。'
    return
  }
  submitting.value = true
  notice.value = ''
  try {
    const sessionId = sessions.currentId
    const fileId = selectedFile.value
    const mode = solverMode.value
    const result = await submitOnce(auth.username, {
      sessionId, message, fileId, mode, presentationMode: parsed.presentationMode,
    })
    if (!result.success || !result.job_id || !result.status) throw new Error(typeof result.error === 'string' ? result.error : '任务未被接受')
    if (sessions.currentId !== sessionId || reportDisposed) return
    jobs.start(result.job_id, sessionId, result.status, 0, parsed.presentationMode ?? null)
    observeJob(result.job_id)
    sessions.addUser(message, result.job_id)
    report.value = null
    draft.value = ''
    selectedFile.value = undefined
    selectedFileName.value = undefined
    await sessions.select(sessions.currentId)
    await loadReport(result.job_id)
  } catch (error) {
    notice.value = `${error instanceof Error ? error.message : '任务提交失败。'} 待确认提交已保留，请核对原提交。`
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
  const target = selectedJob.value
  if (!target || submitting.value) return
  submitting.value = true
  try {
    const result = await api.resumeJob(target.jobId, '', createIdempotencyKey())
    if (!result.success) throw new Error(result.error ?? '恢复失败。')
    jobs.confirmResume(target.jobId)
    if (reportDisposed || sessions.currentId !== target.sessionId) return
    draft.value = ''
    notice.value = result.existing ? '已重放恢复结果。' : '已请求恢复执行；没有追加文本约束。'
    const observed = await api.getJob(target.jobId).catch(() => null)
    if (reportDisposed || sessions.currentId !== target.sessionId) return
    if (observed) {
      jobs.observe(observed)
      // Resume from the refreshed snapshot so old pause/failure events cannot undo the transition.
      jobs.start(target.jobId, target.sessionId, observed.status, observed.last_event_id ?? 0)
    }
    if (!observed || observed.status === 'queued' || observed.status === 'running') observeJob(target.jobId)
    else if (observed.status === 'succeeded') await loadReport(target.jobId)
  } catch (error) { notice.value = error instanceof Error ? error.message : '恢复失败。' }
  finally { submitting.value = false }
}
async function clarificationChanged(jobId: string, nextJobId?: string): Promise<void> {
  const sessionId = sessions.currentId
  if (!sessionId || selectedJob.value?.jobId !== jobId || reportDisposed) return
  report.value = null
  try {
    if (nextJobId) await sessions.select(sessionId)
    if (nextJobId) jobs.observe(await api.getJob(jobId))
    const target = nextJobId ?? jobId
    const observed = await api.getJob(target)
    if (sessions.currentId !== sessionId || reportDisposed) return
    jobs.observe(observed)
    if (observed.status === 'queued' || observed.status === 'running') observeJob(target)
    else if (observed.status === 'succeeded') await loadReport(target)
  } catch (error) { notice.value = error instanceof Error ? error.message : '暂时无法读取任务状态。' }
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
async function loadReport(jobId: string): Promise<void> {
  if (sessions.messages.at(-1)?.analysis_job_id !== jobId) return
  const sessionId = sessions.currentId
  const isCurrent = () => !reportDisposed && sessions.currentId === sessionId
    && sessions.messages.at(-1)?.analysis_job_id === jobId
  try {
    jobs.observe(await api.getJob(jobId))
    const loaded = await api.jobReport(jobId)
    if (isCurrent() && loaded.evidence_id === jobId
        && (loaded.solver?.solver?.state_revision ?? 0) >= (report.value?.solver?.solver?.state_revision ?? 0)) report.value = loaded
  } catch { if (isCurrent()) report.value = null }
}
function observeJob(jobId: string): void {
  void jobController.subscribe(jobId).then(async () => {
    await loadReport(jobId)
    const record = jobs.byId(jobId)
    if (record?.error && selectedJob.value?.jobId === jobId) notice.value = record.error
  })
}
async function refreshActive(): Promise<void> {
  const sessionId = sessions.currentId
  if (!sessionId || reportDisposed) return
  try {
    const response = await api.activeJobs(sessionId)
    if (sessions.currentId !== sessionId || reportDisposed) return
    for (const job of response.jobs ?? []) {
      jobs.observe(job)
      observeJob(job.job_id)
    }
  } catch (error) { notice.value = error instanceof Error ? error.message : '活跃任务查询失败。' }
}
async function recoverSubmission(): Promise<void> {
  const sessionId = sessions.currentId
  if (!sessionId || submitting.value || checkingSubmission.value) return
  const record = readSubmission(auth.username, sessionId)
  if (!record) return
  checkingSubmission.value = true
  notice.value = '正在核对原提交…'
  try {
    const found = await lookupSubmission(record)
    if (sessions.currentId !== sessionId || reportDisposed) return
    if (!found) {
      draft.value = (record.input.presentationMode ? `/${record.input.presentationMode} ` : '') + record.input.message
      selectedFile.value = record.input.fileId
      solverMode.value = record.input.mode
      notice.value = '原提交尚未受理；再次提交将复用同一身份。'
      return
    }
    jobs.observe(found)
    if (!sessions.messages.some(message => message.analysis_job_id === found.job_id)) {
      sessions.addUser(record.input.message, found.job_id)
    }
    await loadReport(found.job_id)
    observeJob(found.job_id)
    notice.value = '已找回原提交。'
  } catch (error) { notice.value = `原提交核对失败，未创建新任务。${error instanceof Error ? error.message : ''}` }
  finally { checkingSubmission.value = false }
}
async function solveAgain(): Promise<void> {
  const submitted = selectedJob.value && sessions.currentId
    ? readSubmission(auth.username, sessions.currentId)?.input : undefined
  const input = {
    draft: submitted
      ? (submitted.presentationMode ? `/${submitted.presentationMode} ` : '') + submitted.message
      : selectedProblem.value || draft.value,
    fileId: submitted ? submitted.fileId : selectedFile.value,
    fileName: selectedFileName.value,
    mode: submitted ? submitted.mode : solverMode.value,
  }
  try {
    const id = await sessions.create()
    sessionStorage.setItem(`mathagent:resolve:${id}`, JSON.stringify(input))
    globalThis.history.pushState({}, '', sessionHref(id))
    globalThis.dispatchEvent(new PopStateEvent('popstate'))
  } catch (error) { notice.value = error instanceof Error ? error.message : '创建新求解失败。' }
}
function onVisibility(): void { if (document.visibilityState === 'visible') { void refreshActive(); void recoverSubmission() } }
async function initialize(): Promise<void> {
  loading.value = true
  loadFailed.value = false
  notice.value = ''
  try {
  try {
    const capabilities = await api.capabilities()
    faithful.value = capabilities.faithful?.enabled ? capabilities.faithful : undefined
    solverMode.value = faithful.value?.solver_mode ?? 'legacy'
    if (capabilities.execution?.mode === 'live' && capabilities.execution.status !== 'configured') {
      notice.value = 'live 模式未检测到 Intern API 凭证。'
    }
    solverModes.value = capabilities.solver_modes ?? []
    presentationEnabled.value = capabilities.presentation?.enabled ?? false
    visionEnabled.value = capabilities.files.upload.enabled
    if (visionEnabled.value) await files.load()
  } catch (error) {
    loadFailed.value = true
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
  const freshDraftKey = `mathagent:resolve:${sessions.currentId}`
  const freshInput = sessionStorage.getItem(freshDraftKey)
  if (freshInput) {
    const input = JSON.parse(freshInput) as { draft: string; fileId?: string; fileName?: string; mode: string }
    draft.value = input.draft
    selectedFile.value = input.fileId
    selectedFileName.value = input.fileName ?? input.fileId
    solverMode.value = input.mode
    sessionStorage.removeItem(freshDraftKey)
  }
  await recoverSubmission()
  await refreshActive()
  const latest = sessions.messages.at(-1)
  if (latest?.analysis_job_id) {
    try {
      jobs.observe(await api.getJob(latest.analysis_job_id))
      const restored = jobs.byId(latest.analysis_job_id)
      if (restored) restored.replay = ['succeeded', 'failed', 'canceled'].includes(restored.status)
    } catch (error) {
      notice.value = error instanceof Error ? error.message : '任务状态加载失败。'
    }
    await loadReport(latest.analysis_job_id)
    observeJob(latest.analysis_job_id)
  }
  } catch (error) { loadFailed.value = true; notice.value = error instanceof Error ? error.message : '会话加载失败，请重试。' }
  finally { loading.value = false }
}
onMounted(() => { void initialize(); document.addEventListener('visibilitychange', onVisibility) })
onUnmounted(() => { reportDisposed = true; jobController.stopAll(); document.removeEventListener('visibilitychange', onVisibility) })
</script>

<template>
  <div class="constellation-shell" data-workspace="conversation-workbench">
    <a class="skip-link" href="#main-content">跳到主要内容</a>
    <SessionSidebar :items="sessions.items" :current-id="sessions.currentId" :open="sidebarOpen" @new="newSession" @select="selectSession" @rename="rename" @remove="remove" @settings="openSettings" @close="sidebarOpen = false" />
    <main id="main-content" tabindex="-1" class="constellation-page">
      <header class="constellation-topbar">
        <UiButton icon-only variant="ghost" class="mobile-only" aria-label="打开会话栏" @click="sidebarOpen = true"><UiIcon name="menu" /></UiButton>
        <div><small>MATHAGENT · 数学推理工作台</small><h1>{{ selectedJob ? '对话式求解工作台' : '新建求解 · 输入题干' }}</h1></div>
        <div class="constellation-actions"><span>{{ current?.status === 'waiting_input' ? '等待输入' : current ? '任务执行中' : selectedJob ? '持久运行记录' : '准备提交' }}</span><UiButton v-if="current && clarification?.clarification.status !== 'waiting'" variant="danger" @click="cancelCurrent">取消任务</UiButton><UiButton v-if="selectedJob" @click="newSession">新建求解</UiButton><UiButton v-if="selectedJob || notice" :disabled="submitting || checkingSubmission || !!current" @click="solveAgain">再次求解</UiButton><a v-if="selectedJob" :href="`/dashboard/run/${selectedJob.jobId}`">运行详情</a></div>
      </header>
      <p v-if="notice" class="notice" role="status">{{ notice }}<UiButton v-if="!loadFailed && !submitting && !checkingSubmission" @click="recoverSubmission">核对原提交</UiButton><UiButton v-if="loadFailed" @click="initialize">重新加载</UiButton></p>
      <p v-if="current?.status === 'waiting_input' && !clarification" class="notice notice--warning" role="status">运行已暂停。恢复执行不会追加新约束。<UiButton :disabled="submitting" @click="resumeCurrent">恢复执行</UiButton></p>
      <div v-if="loading" class="loading-state" role="status">正在加载工作台…</div>
      <section v-else-if="!selectedJob" class="workbench-entry" aria-label="提交数学题干">
        <div class="entry-heading"><small>{{ faithful ? 'FAITHFUL AGENT' : 'PLANNER → REASONER → GATE' }}</small><h2>{{ faithful ? 'Faithful 自主求解' : '把题干交给一组会互相质疑的子智能体' }}</h2><p>{{ faithful ? '直接输入数学题，Faithful 自主选择已配置能力与求解步骤。提交后可查看公开执行摘要、实时计划与协作星图。' : '提交后查看公开执行摘要、实时计划与协作星图。运行能力取决于所选模式；模拟数据和历史回放始终单独标记。' }}</p></div>
        <ComposerBar :submit-label="checkingSubmission ? '正在核对…' : submitting ? '正在提交…' : autonomous ? 'Faithful 自主求解' : '开始求解'" v-model="draft" :disabled="loadFailed || submitting || checkingSubmission" :busy="submitting || checkingSubmission" :submit-disabled="faithfulBlocked" :running="false" :vision-enabled="visionEnabled" :selected-file-name="selectedFileName" @submit="send" @cancel="cancelCurrent" @upload="chooseFile" @clear-file="clearFile"><template #mode><FaithfulEntryControls v-if="faithful" v-model="solverMode" :faithful="faithful" :modes="solverModes" :disabled="submitting" /><StarModeSelector v-else v-model="solverMode" :modes="solverModes" :disabled="submitting" /><PresentationCommandHint :enabled="presentationEnabled" /></template></ComposerBar>
        <div class="entry-examples"><span>示例题干 · 点击回填</span><button type="button" @click="useStarter('解方程 x² − 5x + 6 = 0，并验证候选根。')">方程与候选根</button><button type="button" @click="useStarter('分步推导 1 + 2 + … + n 的求和公式，n 为正整数。')">数列求和</button></div>
      </section>
      <section v-else class="active-workbench">
        <article class="workbench-problem"><small>当前题干</small><p>{{ selectedProblem }}</p></article>
        <ClarificationPanel v-if="clarification" :key="clarification.clarification.request_id" :state="clarification" :resuming="submitting" @resume="resumeCurrent" @changed="clarificationChanged" @cancel="cancelCurrent" />
        <TaskRevisionPanel :key="selectedJob.jobId + ':revision'" :job-id="selectedJob.jobId" :session-id="selectedJob.sessionId" :owner="auth.username" :mode="solverMode" :state="selectedJob.result?.faithful" :disabled="submitting || checkingSubmission" @changed="clarificationChanged" />
        <ConversationWorkbench :key="selectedJob.jobId" :events="selectedJob.events" :result="workbenchResult" :replay="selectedJob.replay" :status="selectedJob.status" :error="selectedJob.error" />
        <PresentationSection :source-version="showReport" v-if="showReport && presentationMode" :job-id="selectedJob.jobId" :mode="presentationMode" :job-status="selectedJob.status" :problem="selectedProblem" :fallback-answer="showReport.report.answer" />
        <ReportSection v-else-if="showReport" :mode="showReport.mode" :status="showReport.status" :report="showReport.report" />
      </section>
    </main>
  </div>
</template>

<style scoped>
.constellation-shell { display: grid; grid-template-columns: 232px minmax(0, 1fr); height: 100dvh; overflow: hidden; background: var(--background); }
.constellation-page { display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow-y: auto; }
.constellation-topbar { display: flex; align-items: center; gap: 12px; justify-content: space-between; padding: 14px 24px; border-bottom: 1px solid var(--border); background: var(--surface); }
.constellation-topbar small, .entry-heading > small { font: 10px var(--font-mono); letter-spacing: .12em; color: var(--muted); }
h1 { margin: 6px 0 0; font-size: 15px; }
.constellation-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; font-size: 12px; color: var(--muted); }
.workbench-entry { width: min(720px, calc(100% - 40px)); margin: auto; padding: 64px 0; }
.entry-heading { text-align: center; margin-bottom: 24px; }
.entry-heading h2 { font-size: clamp(22px, 2.2vw, 30px); line-height: 1.4; margin: 16px 0 8px; }
.entry-heading p { max-width: 54ch; margin: auto; font-size: 13px; line-height: 1.8; color: var(--muted); }
.workbench-entry :deep(.composer-shell) { width: 100%; margin: 0; box-shadow: var(--shadow-overlay); background: var(--surface); }
.workbench-entry :deep(textarea) { min-height: 160px; }
.entry-examples { display: flex; justify-content: center; flex-wrap: wrap; gap: 8px; margin-top: 40px; font-size: 12px; color: var(--muted); }
.entry-examples > span { flex-basis: 100%; text-align: center; }
.entry-examples button { padding: 8px 12px; border: 1px dashed var(--border-strong); border-radius: var(--radius-md); color: var(--muted); background: transparent; cursor: pointer; }
.active-workbench { padding: 16px 24px 32px; }
.workbench-problem { padding: 12px 16px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface); }
.workbench-problem small { color: var(--muted); font-size: 11px; }
.workbench-problem p { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 14px; line-height: 1.7; margin: 6px 0; }
@media(max-width: 760px) { .constellation-shell { grid-template-columns: minmax(0, 1fr); } .constellation-topbar { padding: 12px; flex-wrap: wrap; } .constellation-actions { gap: 8px; } .active-workbench { padding: 12px; } .workbench-entry { padding: 32px 0; } }
</style>
