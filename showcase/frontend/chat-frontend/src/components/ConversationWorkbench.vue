<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, shallowRef, watch } from 'vue'
import type { DecodedSseEvent } from '../api/events.schemas'
import type { Collaboration } from '../api/workbench.schemas'
import { eventRole, roleLabels, statusLabels, typeOf } from '../runtime/jobs/causal-progress'
import { projectWorkbench, roles } from '../runtime/jobs/workbench'
import AgentConstellation from './AgentConstellation.vue'
import RoleStagePanel from './RoleStagePanel.vue'
import AutonomousRouteStatus from './AutonomousRouteStatus.vue'
import SerialInterventionStatus from './SerialInterventionStatus.vue'

const props = defineProps<{ jobId?: string; executionMode?: string; events: DecodedSseEvent[]; result?: unknown; replay?: boolean; status: string; error?: string | null; animateLive?: boolean; ordinary?: boolean }>()
const readingRole = ref('planner')
const readingSource = ref<string>()
const panel = ref<InstanceType<typeof RoleStagePanel>>()
const progressControl = ref<HTMLButtonElement>()
const savedSource = computed(() => props.events.filter(event =>
  ['initial_plan_generated', 'plan_replaced', 'step_reported', 'step_reviewed', 'explore_assessed',
    'solution_review_assessed', 'final_candidate_generated', 'final_candidate_reviewed', 'finalization_completed',
    'meta_decided', 'meta_guidance_decided', 'meta_guidance_applied', 'trace_back_applied', 'plan_archived',
    'reexploration_completed', 'counterexample_completed', 'formal_verification_completed'].includes(typeOf(event))
  && (eventRole(event) === readingRole.value || readingRole.value === 'controller' && eventRole(event) === 'planner')
  && typeof event.data.role_stage_source === 'string' && /^[0-9a-f]{64}$/.test(event.data.role_stage_source)
).at(-1)?.data.role_stage_source as string | undefined)
async function openRole(value: string, source?: string) {
  if (!roles.some(item => item[0] === value)) return
  const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : undefined
  const fallback = trigger?.closest<HTMLElement>('.constellation') ?? progressControl.value
  readingRole.value = value
  readingSource.value = source
  await nextTick()
  panel.value?.open(trigger, fallback)
}
const view = ref(props.ordinary ? 'constellation' : 'conversation')
const role = ref('')
const step = ref('')
const expanded = ref(false)
const technical = ref(false)
const page = ref(1)
const replayCount = ref<number | null>(null)
const playing = ref(false)
let timer: ReturnType<typeof setInterval> | undefined
// Batch display updates only; the store and durable cursor retain every event.
const displayEvents = shallowRef(props.events.slice())
let displayTimer: ReturnType<typeof setTimeout> | undefined
const all = computed(() => projectWorkbench(displayEvents.value, props.result, Boolean(props.replay), props.status))
const state = computed(() => replayCount.value === null ? all.value : projectWorkbench(all.value.events.slice(0, replayCount.value), null, true))
const now = ref(Date.now())
const phaseClock = setInterval(() => { now.value = Date.now() }, 1000)
const elapsed = computed(() => state.value.phaseStartedAt === null ? '阶段耗时未知'
  : props.replay || replayCount.value !== null || props.status !== 'running' ? '历史阶段记录'
    : `本阶段 ${Math.max(0, Math.floor((now.value - state.value.phaseStartedAt) / 1000))} 秒`)
const filtered = computed(() => state.value.keyEntries.filter(entry => (!role.value || entry.role === role.value
  || entry.message?.from_role === role.value || entry.message?.to_role === role.value) && (!step.value || entry.step === step.value)))
const shown = computed(() => expanded.value ? filtered.value : filtered.value.slice(-6))
const technicalEntries = computed(() => state.value.entries.slice((page.value - 1) * 100, page.value * 100))
const flights = ref<Collaboration[]>([])
const motionEnabled = ref(true)
const systemAllowsMotion = ref(true)
const eligibleEvents = new Set<number>()
const flightTimers = new Map<string, ReturnType<typeof setTimeout>>()
const displayedMessages = computed(() => state.value.entries.flatMap(entry => entry.message ? [entry.message] : []))
const motionActive = computed(() => view.value === 'constellation' && motionEnabled.value && systemAllowsMotion.value
  && props.animateLive && !props.replay && replayCount.value === null)
function clearFlights() {
  eligibleEvents.clear()
  flightTimers.forEach(clearTimeout)
  flightTimers.clear()
  flights.value = []
}
watch(motionActive, active => { if (!active) clearFlights() }, { flush: 'sync' })
const provenance = computed(() => {
  if (all.value.source.startsWith('FAKE') || props.executionMode === 'fake') return '模拟运行'
  if (all.value.source.startsWith('LIVE') || props.executionMode === 'live') {
    return !props.replay && replayCount.value === null && ['queued', 'running'].includes(props.status)
      ? '实时运行' : '真实历史记录'
  }
  return '来源待确认'
})
const dark = ref(globalThis.document?.documentElement.dataset.theme === 'dark')
function toggleTheme() {
  dark.value = !dark.value
  document.documentElement.dataset.theme = dark.value ? 'dark' : 'light'
  try { localStorage.setItem('mathagent-theme', dark.value ? 'dark' : 'light') } catch { /* Optional persistence. */ }
}
// Record visibility at arrival. Switching views during the display batch must not replay a handoff.
watch(() => props.events.length, (length, previous) => {
  if (motionActive.value && length > previous) {
    for (const event of props.events.slice(previous, length)) {
      if (event.id !== null) eligibleEvents.add(event.id)
    }
  }
  if (displayTimer === undefined) {
    displayTimer = setTimeout(() => { displayTimer = undefined; displayEvents.value = props.events.slice() }, 100)
  }
}, { flush: 'sync' })
const seenMessages = new Set(all.value.entries.flatMap(entry => entry.message ? [entry.message.message_id] : []))
watch(displayEvents, () => {
  const batch: Collaboration[] = []
  for (const entry of all.value.entries) {
    if (entry.message && !seenMessages.has(entry.message.message_id)) {
      seenMessages.add(entry.message.message_id)
      if (entry.event.id !== null && eligibleEvents.has(entry.event.id)) batch.push(entry.message)
    }
  }
  eligibleEvents.clear()
  if (!batch.length) return
  flights.value = [...flights.value, ...batch]
  for (const message of batch) {
    const id = message.message_id
    flightTimers.set(id, setTimeout(() => {
      flights.value = flights.value.filter(item => item.message_id !== id)
      flightTimers.delete(id)
    }, 2500))
  }
})
function selectRole(value: string) { openRole(value) }
function pause() { clearInterval(timer); playing.value = false }
function play() {
  pause()
  if (replayCount.value === null || replayCount.value >= all.value.events.length) replayCount.value = 0
  playing.value = true
  timer = setInterval(() => {
    replayCount.value = (replayCount.value ?? 0) + 1
    if (replayCount.value >= all.value.events.length) pause()
  }, 900)
}
onUnmounted(() => { pause(); clearFlights(); clearTimeout(displayTimer); clearInterval(phaseClock) })
</script>

<template>
  <section class="workbench" aria-label="对话式执行工作台">
    <RoleStagePanel ref="panel" :job-id="jobId" :role="readingRole" :source="readingSource" :saved-source="savedSource" :revision="events.length" :job-status="status" :runtime-state="state.roleStates[readingRole]" @filter="role = $event" />
    <header class="workbench-toolbar">
      <strong>{{ ordinary ? (replay || replayCount !== null ? '历史回放' : '求解进展') + ' · ' + provenance : replayCount === null ? all.source : 'REPLAY · 本地事件回放' }}</strong>
      <span role="status" aria-atomic="true">当前阶段：{{ state.phase }}<span v-if="error"> · 请刷新任务状态</span></span>
      <small>{{ elapsed }}</small>
      <div class="view-controls" aria-label="执行视图">
        <button type="button" :aria-pressed="dark" @click="toggleTheme">{{ dark ? '浅色主题' : '深色主题' }}</button>
        <button ref="progressControl" type="button" :aria-pressed="view === 'conversation'" @click="view = 'conversation'">关键进展</button>
        <button type="button" :aria-pressed="view === 'constellation'" @click="view = 'constellation'">完整星图</button>
      </div>
    </header>
    <p v-if="['waiting_input', 'failed', 'canceled', 'unknown', 'needs_review'].includes(status)" class="attention">{{ statusLabels[status] }}。请查看任务状态及当前允许的操作；结果未知时先核对原提交，不要自动重发。</p>
    <div class="workbench-columns" :class="{ 'full-graph': view === 'constellation' }">
      <div class="workbench-main">
        <div class="event-filters">
          <label>角色 <select v-model="role"><option value="">全部角色</option><option v-for="item in roles" :key="item[0]" :value="item[0]">{{ item[1] }}</option></select></label>
          <label>步骤 <select v-model="step"><option value="">全部步骤</option><option v-for="item in state.steps" :key="item.label">{{ item.label }}</option></select></label>
          <button type="button" @click="role = ''; step = ''">清除筛选</button>
        </div>
        <AgentConstellation v-show="view === 'constellation'" v-model:motion-enabled="motionEnabled" :selected="role" :role-states="state.roleStates" :messages="displayedMessages" :flights="flights" @system-motion="systemAllowsMotion = $event" @select="selectRole" />
        <ol v-show="view === 'conversation'" class="conversation-events">
          <li v-for="entry in shown" :key="entry.event.id!" :data-thread-id="ordinary ? undefined : entry.message?.thread_id">
            <article :data-workbench-event="ordinary ? undefined : entry.event.id">
              <small><button v-if="roles.some(item => item[0] === entry.role)" type="button" :aria-label="`查看${roleLabels[entry.role]}阶段成果`" @click="openRole(entry.role, typeof entry.event.data.role_stage_source === 'string' ? entry.event.data.role_stage_source : '')">{{ roleLabels[entry.role] }}</button><template v-else>{{ roleLabels[entry.role] }}</template> <span v-if="entry.step">· {{ entry.step }}</span></small>
              <h3>{{ entry.title }}</h3><p v-if="entry.summary !== entry.title">{{ entry.summary }}</p>
              <p v-if="entry.message">{{ roleLabels[entry.message.from_role] ?? '角色待确认' }} → {{ roleLabels[entry.message.to_role] ?? '角色待确认' }}</p>
              <p v-if="entry.evidence.length">步骤检查允许推进，不等于整题正确或形式化证明。</p>
            </article>
          </li>
        </ol>
        <p v-if="!shown.length">等待关键进展；请稍候或刷新任务状态。</p>
        <button v-if="filtered.length > 6" type="button" :aria-expanded="expanded" @click="expanded = !expanded">{{ expanded ? '收起完整过程' : `展开完整过程（${filtered.length} 项）` }}</button>
        <details v-if="!ordinary" @toggle="technical = ($event.target as HTMLDetailsElement).open">
          <summary>技术详情（{{ state.events.length }} 条公开记录）</summary>
          <template v-if="technical">
            <p>仅显示公开事件身份、类型和分类，不展开模型正文。事件数不等于模型调用数。</p>
            <ol class="technical-records"><li v-for="entry in technicalEntries" :key="entry.event.id!">#{{ entry.event.id }} · {{ typeOf(entry.event) }} · {{ roleLabels[entry.role] }} · {{ entry.event.data.created_at ?? '时间未知' }} · {{ state.keyEntries.some(e => e.event.id === entry.event.id) ? '关键进展' : '内部记录' }}</li></ol>
            <button type="button" :disabled="page <= 1" @click="page--">上一页</button><span>第 {{ page }} 页</span>
            <button type="button" :disabled="page * 100 >= state.events.length" @click="page++">下一页</button>
          </template>
        </details>
      </div>
      <aside class="workbench-plan" aria-label="求解计划">
        <details><summary>求解计划与调度详情</summary>
        <AutonomousRouteStatus v-if="!ordinary" :execution-switch="state.progress.execution_switch" :selection="state.progress.execution_selection" :population="state.progress.population" />
        <SerialInterventionStatus v-if="!ordinary" :value="state.progress.serial_intervention" />
        <h3>求解计划</h3>
        <p v-if="!state.steps.length">计划尚未生成</p>
        <p v-else class="interjection-note">目标来自已保存的计划；执行状态来自实际核验事件。</p>
        <ol><li v-for="item in state.steps" :key="item.label" :data-step-status="item.status"><strong>{{ item.label }}</strong><p v-if="item.goal">{{ item.goal }}</p><span>{{ statusLabels[item.status] ?? '状态待确认' }}</span></li></ol>
        <details v-if="!ordinary && status === 'failed' && state.partial.unresolved.length">
          <summary>已保存成果与未解决项</summary>
          <p>已核验：{{ state.partial.accepted.join('、') || '暂无' }}</p>
          <p>未解决：{{ state.partial.unresolved.map(item => item === 'whole_solution_review' ? '独立整题审查' : item).join('、') }}</p>
          <article v-for="(candidate, i) in state.partial.candidates" :key="i"><small>候选 {{ i + 1 }} · {{ candidate.review }} · {{ candidate.eligible ? '已通过审查' : '未获通过' }}</small><p>{{ candidate.text }}</p></article>
        </details>
        </details>
        <AgentConstellation v-show="view === 'conversation'" mini :selected="role" :role-states="state.roleStates" :messages="displayedMessages" @select="selectRole" />
        <p class="interjection-note">节点依据公开生命周期更新；历史在途状态不冒充实时执行。</p>
      </aside>
    </div>
    <details class="replay-controls"><summary>查看历史回放</summary>
      <button type="button" :disabled="!all.events.length" @click="playing ? pause() : play()">{{ playing ? '暂停回放' : '回放已收事件' }}</button>
      <label>回放位置（不是求解进度） <input type="range" min="0" :max="all.events.length" :value="replayCount ?? all.events.length" @input="pause(); replayCount = Number(($event.target as HTMLInputElement).value)" /></label>
      <button v-if="replayCount !== null" type="button" @click="pause(); replayCount = null; clearFlights()">返回任务状态</button>
    </details>
  </section>
</template>

<style scoped>
.workbench { margin: 16px 0; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); color: var(--text); }
.workbench-toolbar, .event-filters, .replay-controls, .view-controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.workbench-toolbar, .replay-controls { padding: 12px; background: var(--surface-muted); }
.workbench-toolbar { position: sticky; top: 0; z-index: 2; }
.technical-records { font-size: 12px; overflow-wrap: anywhere; }
.attention { padding: 12px; }
summary { cursor: pointer; padding: 8px 0; }
.workbench-toolbar > strong { color: var(--accent); font: 12px var(--font-mono); }
.view-controls { margin-left: auto; }
button, select { background: var(--surface); color: var(--text); border: 1px solid var(--border-strong); border-radius: var(--radius-sm); padding: 6px 8px; font: inherit; min-height: 36px; cursor: pointer; }
button[aria-pressed=true] { border-color: var(--accent); color: var(--accent); }
button:focus-visible, select:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.workbench-columns { display: grid; grid-template-columns: minmax(0, 1fr) 230px; }
.workbench-columns.full-graph { grid-template-columns: minmax(0, 1fr); }
.full-graph .workbench-plan { position: static; border-left: 0; }
.workbench-main { padding: 16px; min-width: 0; }
.workbench-plan { align-self: start; position: sticky; top: 0; padding: 12px; border-left: 1px solid var(--border); }
.workbench-plan h3 { margin: 0 0 12px; }
.workbench-plan ol { padding-left: 20px; }
.workbench-plan li { padding: 8px 0; }
.workbench-plan li span { display: block; font-size: 12px; color: var(--muted); }
[data-step-status=pass] strong { color: var(--success); }
[data-step-status=challenged] strong { color: var(--danger); }
.conversation-events { list-style: none; margin: 16px 0 0; padding: 0 0 0 12px; border-left: 1px solid var(--border-strong); }
.conversation-events > li { padding: 12px; border-bottom: 1px solid var(--border); overflow-wrap: anywhere; }
h3 { font-size: 14px; margin: 6px 0; }
p { white-space: pre-wrap; line-height: 1.65; font-size: 13px; margin: 6px 0; overflow-wrap: anywhere; }
small, .interjection-note { font-size: 11px; color: var(--muted); }
.replay-controls label { display: flex; gap: 8px; font-size: 12px; align-items: center; }
@media(max-width: 900px) { .workbench-columns { grid-template-columns: minmax(0, 1fr); } .workbench-plan { grid-row: 1; position: static; border-left: 0; border-bottom: 1px solid var(--border); } .workbench-plan :deep(.constellation) { max-width: 320px; margin: auto; } }
</style>
