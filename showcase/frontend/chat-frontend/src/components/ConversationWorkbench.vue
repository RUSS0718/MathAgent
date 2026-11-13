<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import type { DecodedSseEvent } from '../api/events.schemas'
import type { Collaboration } from '../api/workbench.schemas'
import { projectWorkbench, roles } from '../runtime/jobs/workbench'
import AgentConstellation from './AgentConstellation.vue'

const props = defineProps<{ events: DecodedSseEvent[]; result?: unknown; replay?: boolean; status: string; error?: string | null }>()
const view = ref('conversation')
const role = ref('')
const step = ref('')
const replayCount = ref<number | null>(null)
const playing = ref(false)
let timer: ReturnType<typeof setInterval> | undefined
const all = computed(() => projectWorkbench(props.events, props.result, Boolean(props.replay)))
const state = computed(() => replayCount.value === null ? all.value : projectWorkbench(all.value.events.slice(0, replayCount.value), null, true))
const shown = computed(() => state.value.entries.filter(entry => (!role.value || entry.role === role.value
  || entry.message?.from_role === role.value || entry.message?.to_role === role.value) && (!step.value || entry.step === step.value)))
const threads = computed(() => {
  const groups: Array<{ id: string; key: string; entries: typeof shown.value }> = []
  for (const entry of shown.value) {
    const id = entry.message?.thread_id ?? `event-${entry.event.id}`
    const previous = groups.at(-1)
    if (previous?.id === id) previous.entries.push(entry)
    else groups.push({ id, key: `${id}:${entry.event.id}`, entries: [entry] })
  }
  return groups
})
const activeRoles = computed(() => [...new Set(state.value.entries.map(entry => entry.role))])
const message = ref<Collaboration | null>(null)
const displayedMessage = computed(() => replayCount.value === null ? message.value : state.value.entries.at(-1)?.message ?? null)
const dark = ref(globalThis.document?.documentElement.dataset.theme === 'dark')
function toggleTheme() {
  dark.value = !dark.value
  document.documentElement.dataset.theme = dark.value ? 'dark' : 'light'
  try { localStorage.setItem('mathagent-theme', dark.value ? 'dark' : 'light') } catch { /* Optional persistence. */ }
}
const animated = new Set<string>()
watch(() => props.events.length, () => {
  for (const entry of all.value.entries) {
    if (entry.message && !animated.has(entry.message.message_id)) {
      animated.add(entry.message.message_id)
      if (!props.replay && replayCount.value === null) message.value = entry.message
    }
  }
})
function selectRole(value: string) { role.value = role.value === value ? '' : value }
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
onUnmounted(pause)
</script>

<template>
  <section class="workbench" aria-label="对话式执行工作台">
    <header class="workbench-toolbar">
      <strong>{{ replayCount === null ? all.source : 'REPLAY · 本地事件回放' }}</strong>
      <span role="status">{{ status }}<span v-if="error"> · {{ error }}</span></span>
      <div class="view-controls" aria-label="执行视图">
        <button type="button" :aria-pressed="dark" @click="toggleTheme">{{ dark ? '浅色主题' : '深色主题' }}</button>
        <button type="button" :aria-pressed="view === 'conversation'" @click="view = 'conversation'">对话事件</button>
        <button type="button" :aria-pressed="view === 'constellation'" @click="view = 'constellation'">完整星图</button>
      </div>
    </header>
    <div class="workbench-columns">
      <div class="workbench-main">
        <div class="event-filters">
          <label>角色 <select v-model="role"><option value="">全部角色</option><option v-for="item in roles" :key="item[0]" :value="item[0]">{{ item[1] }}</option></select></label>
          <label>步骤 <select v-model="step"><option value="">全部步骤</option><option v-for="item in state.steps" :key="item.label">{{ item.label }}</option></select></label>
          <button type="button" @click="role = ''; step = ''">清除筛选</button>
        </div>
        <AgentConstellation v-show="view === 'constellation'" :selected="role" :active-roles="activeRoles" :message="displayedMessage" @select="selectRole" />
        <p v-if="role" class="role-detail">{{ roles.find(item => item[0] === role)?.[1] }} · {{ shown.length }} 条关联公开事件；节点亮起仅代表持久事件已到达。</p>
        <ol v-show="view === 'conversation'" class="conversation-events" aria-live="polite">
          <li v-for="thread in threads" :key="thread.key" :data-thread-id="thread.id">
            <article v-for="entry in thread.entries" :key="entry.event.id!" :data-workbench-event="entry.event.id">
            <small>#{{ entry.event.id }} · {{ entry.role }} <span v-if="entry.step">· {{ entry.step }}</span></small>
            <h3>{{ entry.title }}</h3><p>{{ entry.summary }}</p>
            <template v-if="entry.message">
              <small>{{ entry.message.from_role }} → {{ entry.message.to_role }} · {{ entry.message.thread_status }}</small>
              <details><summary>关联线程与公开边界</summary><p>{{ entry.message.thread_id }}</p><p>计划 v{{ entry.message.plan_version }} · 尝试 {{ entry.message.attempt_index }}；详细正文及裁决依据尚未公开。</p></details>
              <p v-if="entry.message.chosen">裁决：{{ entry.message.chosen }}</p>
              <ul v-if="entry.message.changes"><li v-for="(change, i) in entry.message.changes" :key="i">{{ change.op }} · {{ change.step_label }} · {{ change.summary }}</li></ul>
            </template>
            <ul v-if="entry.evidence.length" aria-label="通过门控的证据步骤"><li v-for="evidence in entry.evidence" :key="evidence.step_label">{{ evidence.step_label }} · ACCEPT · 已允许推进（不等于形式化证明）</li></ul>
            </article>
          </li>
        </ol>
        <p v-if="!shown.length">等待公开执行事件；当前没有匹配的事件。</p>
      </div>
      <aside class="workbench-plan" aria-label="Planner 计划">
        <h3>Planner <small>v{{ state.progress.plan_version ?? '—' }} · 尝试 {{ state.progress.attempt_index ?? '—' }}</small></h3>
        <p v-if="!state.steps.length">计划尚未生成</p>
        <p v-else class="interjection-note">目标来自已保存的计划；执行状态来自实际核验事件。</p>
        <ol><li v-for="item in state.steps" :key="item.label" :data-step-status="item.status"><strong>{{ item.label }}</strong><p v-if="item.goal">{{ item.goal }}</p><span>{{ item.status }}</span></li></ol>
        <details v-if="status === 'failed' && state.partial.unresolved.length">
          <summary>已保存成果与未解决项</summary>
          <p>已核验：{{ state.partial.accepted.join('、') || '暂无' }}</p>
          <p>未解决：{{ state.partial.unresolved.map(item => item === 'whole_solution_review' ? '独立整题审查' : item).join('、') }}</p>
          <article v-for="(candidate, i) in state.partial.candidates" :key="i"><small>候选 {{ i + 1 }} · {{ candidate.review }} · {{ candidate.eligible ? '已通过审查' : '未获通过' }}</small><p>{{ candidate.text }}</p></article>
        </details>
        <AgentConstellation mini :selected="role" :active-roles="activeRoles" :message="displayedMessage" @select="selectRole" />
        <p class="interjection-note">文本插话待接入，当前不能向求解器追加约束。暂停与恢复不代表采纳新文本。</p>
      </aside>
    </div>
    <footer class="replay-controls">
      <button type="button" :disabled="!all.events.length" @click="playing ? pause() : play()">{{ playing ? '暂停回放' : '回放已收事件' }}</button>
      <label>事件进度 <input type="range" min="0" :max="all.events.length" :value="replayCount ?? all.events.length" @input="pause(); replayCount = Number(($event.target as HTMLInputElement).value)" /></label>
      <button v-if="replayCount !== null" type="button" @click="pause(); replayCount = null; message = null">返回任务状态</button>
    </footer>
  </section>
</template>

<style scoped>
.workbench { margin: 16px 0; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); overflow: clip; color: var(--text); }
.workbench-toolbar, .event-filters, .replay-controls, .view-controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.workbench-toolbar, .replay-controls { padding: 12px; background: var(--surface-muted); }
.workbench-toolbar > strong { color: var(--accent); font: 12px var(--font-mono); }
.view-controls { margin-left: auto; }
button, select { background: var(--surface); color: var(--text); border: 1px solid var(--border-strong); border-radius: var(--radius-sm); padding: 6px 8px; font: inherit; min-height: 36px; cursor: pointer; }
button[aria-pressed=true] { border-color: var(--accent); color: var(--accent); }
button:focus-visible, select:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.workbench-columns { display: grid; grid-template-columns: minmax(0, 1fr) 230px; }
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
