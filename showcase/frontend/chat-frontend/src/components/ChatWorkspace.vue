<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api/client'
import type { CapabilitiesResponse } from '../api/capabilities.schemas'
import { faithfulTaskStateSchema, clarificationStateSchema } from '../api/jobs.schemas'
import { lookupSubmission, readSubmission, submitOnce } from '../runtime/jobs/submission'
import { useAuthStore } from '../stores/auth.store'
import { createIdempotencyKey } from '../runtime/jobs/idempotency'
import { sessionHref, settingsHref, workspaceHref } from '../runtime/navigation/app-route'
import { useJobsStore } from '../stores/jobs.store'
import { useSessionsStore } from '../stores/sessions.store'
import { useFilesStore } from '../stores/files.store'
import FinalAnswer from './FinalAnswer.vue'
import { isApiError } from '../api/errors'
import { JobController } from '../runtime/jobs/job-controller'
import { parsePresentationInput } from '../runtime/presentation/mode'
import type { PresentationMode } from '../runtime/presentation/mode'
import SessionSidebar from './SessionSidebar.vue'
import { inputIntakeSchema, problemTypeLabels } from '../api/jobs.schemas'
import ComposerBar from './ComposerBar.vue'
import FaithfulTaskStatus from './FaithfulTaskStatus.vue'
import UiButton from './ui/UiButton.vue'
import UiIcon from './ui/UiIcon.vue'
import ConversationWorkbench from './ConversationWorkbench.vue'
import ClarificationPanel from './ClarificationPanel.vue'
import TaskRevisionPanel from './TaskRevisionPanel.vue'

function ordinaryError(error: unknown, fallback: string): string {
  if (isApiError(error) && (error.code === 'csrf_invalid' || error.code === 'auth_required')) return '会话已失效，请刷新后重试。'
  return fallback
}

const auth = useAuthStore()
const sessions = useSessionsStore()
const jobs = useJobsStore()
const jobController = new JobController(jobs, true)
const files = useFilesStore()
const draft = ref('')
const notice = ref('')
const visionEnabled = ref(false)
const presentationEnabled = ref(false)
const solverMode = ref('')
const faithful = ref<CapabilitiesResponse['faithful']>()
const locallyStartedJob = ref<string | null>(null)
const executionMode = ref<string>()
const faithfulBlocked = computed(() => faithful.value?.enabled === true && !faithful.value.ready)
const selectedFile = ref<string | undefined>()
const selectedFileName = ref<string | undefined>()
const uploadingImage = ref(false)
const imageLimit = ref(0)
const sidebarOpen = ref(false)
const submitting = ref(false)
const checkingSubmission = ref(false)
const loading = ref(true)
const loadFailed = ref(false)
let reportDisposed = false
const props = defineProps<{ path: string; sessionId: string | null }>()
const current = computed(() => sessions.currentId ? jobs.activeForSession(sessions.currentId) : undefined)
const selectedJob = computed(() => {
  if (current.value) return current.value
  const jobId = sessions.messages.at(-1)?.analysis_job_id
  return jobId ? jobs.byId(jobId) : undefined
})
const presentationMode = computed(() => selectedJob.value?.presentationMode ?? null)
const taskState = computed(() => faithfulTaskStateSchema.safeParse(selectedJob.value?.result?.faithful).data)
const clarification = computed(() => clarificationStateSchema.safeParse(selectedJob.value?.result?.faithful).data)
const selectedProblem = computed(() => {
  const jobId = selectedJob.value?.jobId
  return [...sessions.messages].reverse().find((message) => message.analysis_job_id === jobId && message.sender === 'user')?.text ?? ''
})
const workbenchResult = computed(() => selectedJob.value?.result)
const inputIntake = computed(() => inputIntakeSchema.safeParse(workbenchResult.value?.input_intake).data)
const imageIntakeNotice = computed(() => {
  const intake = inputIntake.value
  if (!intake || intake.modality === 'text') return ''
  if (intake.status === 'pending') {
    return selectedJob.value?.status === 'failed' ? '题图读取中断，请重新提交。'
      : selectedJob.value?.status === 'canceled' ? '题图读取已停止。' : '正在读取题图…'
  }
  if (intake.status === 'failed') {
    if (intake.error === 'image_intake_interrupted') return '题图读取中断，原任务不会重发。请重新提交。'
    if (intake.error === 'run_budget_exhausted') return '题图超出当前任务预算，请缩小图片后重新提交。'
    return '未能读取题图，请更换清晰的图片或输入题干后再试。'
  }
  return '已读取题图。'
})
const jobProvenance = computed(() => {
  const job = selectedJob.value
  if (!job) return executionMode.value === 'fake' ? '模拟运行' : executionMode.value === 'live' ? '实时求解入口' : ''
  const mode = job.result?.execution_mode ?? (locallyStartedJob.value === job.jobId ? executionMode.value : undefined)
  if (mode === 'fake' || ['scripted', 'fault_injection'].includes(String(job.result?.evidence_kind))) return '模拟运行'
  if (mode === 'live') return ['queued', 'running'].includes(job.status) ? '实时运行' : '真实历史记录'
  return '来源待确认'
})


async function send(): Promise<void> {
  if (loading.value || loadFailed.value || faithfulBlocked.value) return
  if (current.value?.status === 'waiting_input') { notice.value = '文本插话尚未接入；请使用恢复执行按钮。'; return }
  const parsed = parsePresentationInput(draft.value)
  const message = parsed.problem
  if (parsed.presentationMode && !presentationEnabled.value) {
    notice.value = '所选答复规则当前不可用；题目未提交。'
    return
  }
  if ((!message && !selectedFile.value) || current.value || !sessions.currentId || submitting.value || uploadingImage.value) {
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
    locallyStartedJob.value = result.job_id
    observeJob(result.job_id)
    sessions.addUser(message, result.job_id)
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
  } catch (error) { notice.value = ordinaryError(error, '取消请求未能确认，请刷新任务状态。') }
}
async function refreshTask(): Promise<void> {
  const target = selectedJob.value
  if (!target) return
  try { jobs.observe(await api.getJob(target.jobId)) }
  catch (error) { notice.value = error instanceof Error ? error.message : '任务状态读取失败。' }
}
async function pauseCurrent(): Promise<void> {
  const target = selectedJob.value
  if (!target || submitting.value || !taskState.value?.allowed_actions.includes('pause')) return
  submitting.value = true
  try { await api.requestInterventionPause(target.jobId); await refreshTask() }
  catch (error) { notice.value = ordinaryError(error, '暂停请求未能确认，请刷新任务状态。') }
  finally { submitting.value = false }
}
async function resumeCurrent(): Promise<void> {
  const target = selectedJob.value
  if (!target || submitting.value) return
  submitting.value = true
  try {
    const result = taskState.value?.allowed_actions.includes('resume_intervention')
      ? await api.resumeInterventionParent(target.jobId, createIdempotencyKey())
      : await api.resumeJob(target.jobId, '', createIdempotencyKey())
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
  } catch (error) { notice.value = ordinaryError(error, '恢复请求未能确认，请刷新任务状态。') }
  finally { submitting.value = false }
}
async function clarificationChanged(jobId: string, nextJobId?: string): Promise<void> {
  const sessionId = sessions.currentId
  if (!sessionId || selectedJob.value?.jobId !== jobId || reportDisposed) return
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
async function chooseFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || uploadingImage.value || submitting.value) return
  clearFile()
  notice.value = ''
  if (imageLimit.value && file.size > imageLimit.value) {
    notice.value = `题图大小不能超过 ${Math.floor(imageLimit.value / 1024)} KiB，请裁剪或压缩后重试。`
    return
  }
  uploadingImage.value = true
  try {
    const attached = await files.upload(file)
    selectedFile.value = attached.file_id
    selectedFileName.value = file.name
  } catch (error) {
    notice.value = error instanceof Error ? error.message : '题图上传失败，请重试。'
  } finally { uploadingImage.value = false }
}
function clearFile(): void { selectedFile.value = undefined; selectedFileName.value = undefined }
async function loadReport(jobId: string): Promise<void> {
  if (sessions.messages.at(-1)?.analysis_job_id !== jobId) return
  try {
    jobs.observe(await api.getJob(jobId))
  } catch { /* A later read can restore the saved task. */ }
}
function observeJob(jobId: string): void {
  void jobController.subscribe(jobId, ({ data }) => {
    if (data.stage === 'image_intake_ready') void loadReport(jobId)
  }).then(async () => {
    await loadReport(jobId)
    const record = jobs.byId(jobId)
    if (record?.error && selectedJob.value?.jobId === jobId) notice.value = '进展连接暂不可用，请刷新任务状态；不会自动重发求解。'
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
      if (!record.input.revision) {
        draft.value = (record.input.presentationMode ? `/${record.input.presentationMode} ` : '') + record.input.message
        selectedFile.value = record.input.fileId
        selectedFileName.value = record.input.fileId ? '已附题图' : undefined
      }
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
    fileId: submitted ? submitted.fileId : selectedJob.value?.fileId ?? selectedFile.value,
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
    executionMode.value = capabilities.execution?.mode
    faithful.value = capabilities.faithful?.enabled ? capabilities.faithful : undefined
    solverMode.value = ''
    if (capabilities.execution?.mode === 'live' && capabilities.execution.status !== 'configured') {
      notice.value = 'live 模式未检测到 Intern API 凭证。'
    }
    presentationEnabled.value = capabilities.presentation?.enabled ?? false
    visionEnabled.value = capabilities.files.upload.enabled
    imageLimit.value = capabilities.files.upload.max_bytes ?? 0
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
      // Opening a saved session shows its current task state; replay is an explicit user action.
      if (restored) restored.replay = false
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
        <div class="workspace-heading"><h1>{{ selectedJob ? '求解工作台' : '数学工作区' }}</h1><span v-if="jobProvenance">{{ jobProvenance }}</span></div>
        <div class="constellation-actions"><span v-if="!taskState">{{ current?.status === 'waiting_input' ? '等待输入' : current ? '任务执行中' : selectedJob ? '已保存的求解' : '准备提交' }}</span><UiButton v-if="!taskState && current && clarification?.clarification.status !== 'waiting'" variant="danger" @click="cancelCurrent">取消任务</UiButton><UiButton v-if="selectedJob" @click="newSession">新建求解</UiButton><UiButton v-if="selectedJob || notice" :disabled="submitting || checkingSubmission || !!current" @click="solveAgain">再次求解</UiButton><a v-if="selectedJob && auth.reviewer" :href="`/dashboard/run/${selectedJob.jobId}`">运行详情</a></div>
      </header>
      <p v-if="notice" class="notice" role="status">{{ notice }}<UiButton v-if="!loadFailed && !submitting && !checkingSubmission" @click="recoverSubmission">核对原提交</UiButton><UiButton v-if="loadFailed" @click="initialize">重新加载</UiButton></p>
      <p v-if="!taskState && current?.status === 'waiting_input' && !clarification" class="notice notice--warning" role="status">运行已暂停。恢复执行不会追加新约束。<UiButton :disabled="submitting" @click="resumeCurrent">恢复执行</UiButton></p>
      <FaithfulTaskStatus v-if="taskState" :state="taskState" :busy="submitting" :clarification="clarification?.clarification.status === 'waiting'" @pause="pauseCurrent" @resume="resumeCurrent" @cancel="cancelCurrent" @refresh="refreshTask" />
      <div v-if="loading" class="loading-state" role="status">正在加载工作台…</div>
      <section v-else-if="!selectedJob" class="workbench-entry" aria-label="提交数学题干">
        <div class="entry-heading"><h2>输入数学问题</h2></div>
        <ComposerBar :command-enabled="presentationEnabled" :submit-label="checkingSubmission ? '正在核对…' : submitting ? '正在提交…' : '发送'" v-model="draft" :disabled="loadFailed || submitting || checkingSubmission" :busy="submitting || checkingSubmission" :submit-disabled="faithfulBlocked" :running="false" :vision-enabled="visionEnabled" :has-image="Boolean(selectedFile)" :uploading="uploadingImage" :selected-file-name="selectedFileName" @submit="send" @cancel="cancelCurrent" @upload="chooseFile" @clear-file="clearFile"></ComposerBar>
        <div class="entry-examples"><span>示例题干 · 点击回填</span><button type="button" @click="useStarter('解方程 x² − 5x + 6 = 0，并验证候选根。')"><strong>方程与候选根</strong><span>解方程 x² − 5x + 6 = 0，并验证候选根。</span><UiIcon name="arrowRight" /></button><button type="button" @click="useStarter('分步推导 1 + 2 + … + n 的求和公式，n 为正整数。')"><strong>数列求和</strong><span>分步推导 1 + 2 + … + n 的求和公式。</span><UiIcon name="arrowRight" /></button></div>
      </section>
      <section v-else class="active-workbench">
        <article class="workbench-problem">
          <small>当前题干 · {{ { solve: '求解', teach: '教学', report: '报告' }[presentationMode ?? 'solve'] }}</small>
          <small v-if="inputIntake?.problem_type" class="problem-type">{{ problemTypeLabels[inputIntake.problem_type] }}</small>
          <p v-if="selectedProblem">{{ selectedProblem }}</p>
          <p v-if="imageIntakeNotice" role="status">{{ imageIntakeNotice }}</p>
        </article>
        <ClarificationPanel v-if="clarification" :key="clarification.clarification.request_id" :state="clarification" :resuming="submitting" @resume="resumeCurrent" @changed="clarificationChanged" @cancel="cancelCurrent" />
        <FinalAnswer :status="selectedJob.status" :key="selectedJob.jobId" :job-id="selectedJob.jobId" />
        <TaskRevisionPanel :key="selectedJob.jobId + ':revision'" :job-id="selectedJob.jobId" :session-id="selectedJob.sessionId" :owner="auth.username" :mode="solverMode" :state="selectedJob.result?.faithful" :disabled="submitting || checkingSubmission" @changed="clarificationChanged" />
        <details :key="selectedJob.jobId" open class="execution-process"><summary>求解过程</summary>
        <ConversationWorkbench :key="selectedJob.jobId" :job-id="selectedJob.jobId" :events="selectedJob.events" :result="workbenchResult" :replay="selectedJob.replay" :status="selectedJob.status" :error="selectedJob.error" :animate-live="locallyStartedJob === selectedJob.jobId" :execution-mode="locallyStartedJob === selectedJob.jobId ? executionMode : undefined" ordinary />
        </details>
      </section>
    </main>
  </div>
</template>

<style scoped>
.constellation-shell { display: grid; grid-template-columns: 264px minmax(0, 1fr); height: 100dvh; overflow: hidden; background: var(--background); }
.constellation-page { display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow-y: auto; }
.constellation-topbar { display: flex; align-items: center; gap: 12px; justify-content: space-between; padding: 14px 24px; border-bottom: 1px solid var(--border); background: var(--surface); }
.constellation-topbar small, .entry-heading > small { font: 10px var(--font-mono); letter-spacing: .12em; color: var(--muted); }
.workspace-heading { display: flex; align-items: baseline; flex-wrap: wrap; gap: 8px 12px; }
.workspace-heading span { font-size: 12px; color: var(--muted); }
h1 { margin: 0; font-size: 16px; }
.constellation-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; font-size: 12px; color: var(--muted); }
.workbench-entry { width: min(720px, calc(100% - 40px)); margin: auto; padding: 64px 0; }
.entry-heading { text-align: center; margin-bottom: 24px; }
.entry-heading h2 { font-size: clamp(28px, 3vw, 40px); font-weight: 500; letter-spacing: -.03em; line-height: 1.4; margin: 16px 0 8px; }
.entry-heading p { max-width: 54ch; margin: auto; font-size: 13px; line-height: 1.8; color: var(--muted); }
.workbench-entry :deep(.composer-shell) { width: 100%; margin: 0; box-shadow: 0 12px 36px rgb(26 43 57 / 7%); background: var(--surface); }
.workbench-entry :deep(textarea) { min-height: 160px; }
.entry-examples { display: grid; gap: 0; margin-top: 32px; font-size: 13px; color: var(--muted); }
.entry-examples > span { padding-bottom: 12px; }
.entry-examples button { display: grid; grid-template-columns: 1fr auto; gap: 6px 16px; padding: 18px 0; border: 0; border-top: 1px solid var(--border); color: var(--text); background: transparent; cursor: pointer; text-align: left; }
.entry-examples button span { grid-column: 1; color: var(--muted); line-height: 1.6; }
.entry-examples button .ui-icon { grid-column: 2; grid-row: 1 / 3; align-self: center; }
.entry-examples button:hover { color: var(--accent-strong); }
.entry-examples button:focus-visible { outline: 2px solid var(--accent); outline-offset: 4px; }
.active-workbench { width: min(1100px, 100%); margin-inline: auto; padding: 12px 32px 48px; }
.workbench-problem { padding: 12px 16px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface); }
.workbench-problem small { color: var(--muted); font-size: 11px; }
.problem-type { margin-inline-start: 12px; }
.workbench-problem p { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 14px; line-height: 1.7; margin: 6px 0; }
@media(max-width: 760px) { .constellation-shell { grid-template-columns: minmax(0, 1fr); } .constellation-topbar { padding: 12px; flex-wrap: wrap; } .constellation-actions { gap: 8px; } .active-workbench { padding: 12px; } .workbench-entry { padding: 32px 0; } }
</style>
