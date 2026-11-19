<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { roles, type PublicHandoff } from '../runtime/jobs/workbench'
import type { Collaboration } from '../api/workbench.schemas'
import { roleLabels } from '../runtime/jobs/causal-progress'
const stateLabels: Record<string, string> = { idle: '未参与', running: '执行中', completed: '已完成', failed: '遇到问题', unknown: '结果未知' }
const props = defineProps<{ selected: string; roleStates: Record<string, string>; messages: PublicHandoff[]; flights?: Collaboration[]; mini?: boolean }>()
const motionEnabled = defineModel<boolean>('motionEnabled', { default: true })
const media = globalThis.matchMedia('(prefers-reduced-motion: reduce)')
const reducedMotion = ref(media.matches)
const emit = defineEmits<{ select: [role: string]; systemMotion: [allowed: boolean] }>()
function syncMotion(event: MediaQueryListEvent) {
  reducedMotion.value = event.matches
  emit('systemMotion', !event.matches)
}
onMounted(() => {
  if (props.mini) return
  media.addEventListener('change', syncMotion)
  emit('systemMotion', !media.matches)
})
onUnmounted(() => media.removeEventListener('change', syncMotion))
const effectiveMotion = computed(() => motionEnabled.value && !reducedMotion.value)
function canDraw(message: Collaboration) {
  return message.from_role !== message.to_role && point(message.from_role) && point(message.to_role)
}
const drawableMessages = computed(() => props.messages.filter(({ message }) => canDraw(message)))
const visibleMessages = computed(() => {
  const paths = new Map<string, PublicHandoff>()
  for (const handoff of drawableMessages.value) {
    const { from_role, to_role } = handoff.message
    paths.set(`${from_role}:${to_role}`, handoff)
  }
  return [...paths.values()]
})
const latestArrival = computed(() => drawableMessages.value.at(-1))
const visibleFlights = computed(() => {
  const byId = new Map(drawableMessages.value.map(handoff => [handoff.message.message_id, handoff]))
  return (props.flights ?? []).flatMap(message => {
    const handoff = byId.get(message.message_id)
    return handoff ? [handoff] : []
  })
})
const evidenceDialog = ref<HTMLDialogElement>()
const listHeading = ref<HTMLElement>()
const map = ref<HTMLElement>()
const selectedHandoff = ref<PublicHandoff>()
let invoker: HTMLElement | undefined
function direction({ from_role, to_role }: Collaboration) {
  const name = (role: string) => Object.hasOwn(roleLabels, role) ? roleLabels[role] : '未标识角色'
  return `${name(from_role)} → ${name(to_role)}`
}
function label(handoff: PublicHandoff) {
  return `第 ${handoff.order} 条 · ${direction(handoff.message)} · ${handoff.action}`
}
async function openEvidence(handoff: PublicHandoff, event: MouseEvent) {
  invoker = event.currentTarget as HTMLElement
  selectedHandoff.value = handoff
  await nextTick()
  evidenceDialog.value?.showModal()
}
function closeEvidence() {
  selectedHandoff.value = undefined
  if (invoker?.isConnected && invoker.getClientRects().length) invoker.focus()
  else (listHeading.value ?? map.value)?.focus()
  invoker = undefined
}
function curve(message: Collaboration) {
  const a = point(message.from_role)!
  const b = point(message.to_role)!
  const x = (a[2] + b[2]) / 2
  const y = (a[3] + b[3]) / 2
  return { a, b, x, y, cx: x - (b[3] - a[3]) * .16, cy: y + (b[2] - a[2]) * .16 }
}
function labelPosition(message: Collaboration) {
  const { x, y, cx, cy } = curve(message)
  return { x: (x + cx) / 2, y: (y + cy) / 2 }
}
function trajectory(message: Collaboration) {
  const { a, b, cx, cy } = curve(message)
  return `M ${a[2]} ${a[3]} Q ${cx} ${cy} ${b[2]} ${b[3]}`
}
function point(role: string) { return roles.find(item => item[0] === role) }
</script>

<template>
  <div>
    <div ref="map" class="constellation" tabindex="-1" :class="{ mini, 'motion-off': !effectiveMotion }" :aria-label="mini ? '迷你星图角色成果' : '智能体协作星图'">
      <button v-if="!mini" class="motion-toggle" type="button" :aria-pressed="effectiveMotion" :disabled="reducedMotion" @click="motionEnabled = !motionEnabled">{{ reducedMotion ? '完整星图动效 · 系统已减少动态效果' : '完整星图动效' }}</button>
      <svg v-if="!mini" preserveAspectRatio="none" viewBox="0 0 1000 700" aria-hidden="true">
        <ellipse v-for="r in [150, 245, 330]" :key="r" class="orbit" cx="500" cy="350" :rx="r * 1.3" :ry="r" />
        <line v-for="role in roles.slice(1)" :key="role[0]" x1="500" y1="306" :x2="role[2]" :y2="role[3]" />
        <g v-for="{ message, tone, action } in visibleMessages" :key="message.message_id" :data-decision="tone">
          <path :d="trajectory(message)" class="message-wire"><title>{{ direction(message) }} · {{ action }}</title></path>
          <text v-bind="labelPosition(message)" class="wire-label">{{ action }}</text>
        </g>
        <g v-for="{ message, tone } in visibleFlights" :key="message.message_id" :data-flight="message.message_id" :data-decision="tone">
          <path :d="trajectory(message)" class="message-highlight" />
          <circle v-for="particle in 6" :key="particle" :r="8 - particle" class="message-flight" :style="{ animationDelay: `${(particle - 1) * .045}s`, offsetPath: `path('${trajectory(message)}')`, opacity: 1 - particle * .12 }" />
          <circle class="arrival" :cx="point(message.to_role)![2]" :cy="point(message.to_role)![3]" r="32" />
        </g>
        <circle v-if="!effectiveMotion && latestArrival" class="static-arrival" :data-decision="latestArrival.tone"
          :cx="point(latestArrival.message.to_role)![2]" :cy="point(latestArrival.message.to_role)![3]" r="53" />
      </svg>
      <button v-for="role in roles" :key="role[0]" type="button" :style="{ left: `${role[2] / 10}%`, top: `${role[3] / 7}%` }"
        :class="[roleStates[role[0]], { selected: selected === role[0] }]" :data-role-state="roleStates[role[0]]" :aria-pressed="selected === role[0]"
        :aria-label="`查看${roleLabels[role[0]]} ${stateLabels[roleStates[role[0]] ?? 'idle'] ?? '状态待确认'}阶段成果`" @click="emit('select', role[0])"><span>{{ roleLabels[role[0]] }}</span><small>{{ stateLabels[roleStates[role[0]] ?? 'idle'] ?? '状态待确认' }}</small></button>
    </div>
    <section v-if="!mini && messages.length" class="handoffs">
      <h3 ref="listHeading" tabindex="-1">公开交接</h3>
      <p v-if="!effectiveMotion && latestArrival" class="arrival-note">
        最近抵达 · {{ label(latestArrival) }}
      </p>
      <ol aria-label="公开交接">
        <li v-for="handoff in messages" :key="handoff.message.message_id">
          <button type="button" :data-decision="handoff.tone" aria-haspopup="dialog" @click="openEvidence(handoff, $event)">{{ label(handoff) }}</button>
        </li>
      </ol>
    </section>
    <dialog v-if="!mini" ref="evidenceDialog" class="handoff-detail" aria-label="交接依据" @close="closeEvidence">
      <form method="dialog"><button autofocus>关闭</button></form>
      <template v-if="selectedHandoff">
        <h3>{{ label(selectedHandoff) }}</h3>
        <p v-if="selectedHandoff.message.summary.trim()">{{ selectedHandoff.message.summary }}</p>
        <p v-if="selectedHandoff.objection">{{ selectedHandoff.objection }}</p>
        <p v-else-if="selectedHandoff.message.content_status === 'not_published' || !selectedHandoff.message.summary.trim()">这条交接未公开具体依据。</p>
      </template>
    </dialog>
  </div>
</template>

<style scoped>
.constellation { position: relative; aspect-ratio: 1000 / 700; width: 100%; overflow: hidden; border-radius: var(--radius-lg); background: radial-gradient(ellipse at 50% 45%, #19364b, #081421 75%); isolation: isolate; }
svg { position: absolute; width: 100%; height: 100%; overflow: visible; }
.orbit { fill: none; stroke: #92b7d0; stroke-opacity: .12; stroke-width: 1; }
line { stroke: #80a8c2; stroke-opacity: .25; stroke-dasharray: 2 8; }
[data-decision] { --wire-color: #a3bbd4; }
[data-decision=challenge] { --wire-color: #ffc078; }
[data-decision=rollback] { --wire-color: #ff91a0; }
[data-decision=rollback] .message-wire, [data-decision=rollback] .message-highlight { stroke-dasharray: 6 5; }
[data-decision=approve] { --wire-color: #88d8a5; }
.message-wire { fill: none; stroke: var(--wire-color); stroke-width: 2; opacity: .8; }
.message-highlight { fill: none; stroke: var(--wire-color); stroke-width: 3; opacity: 0; }
.message-flight { fill: var(--wire-color); filter: drop-shadow(0 0 6px var(--wire-color)); }
.arrival { fill: none; stroke: var(--wire-color); stroke-width: 2; opacity: 0; transform-box: fill-box; transform-origin: center; }
.constellation > button:not(.motion-toggle) { position: absolute; transform: translate(-50%, -50%); display: grid; gap: 4px; min-height: 40px; padding: 8px 12px; border: 1px solid #446277; border-radius: var(--radius-md); background: #11283a; color: #c0d2df; cursor: pointer; font: inherit; white-space: nowrap; }
button.running { border-color: #79e4f3; color: #ecfcff; background: #18455a; }
button.completed { border-color: #82d9b0; color: #a4efcb; }
button.failed, button.unknown { border-color: #ffa8ac; color: #ffc3c6; }
button.selected { background: #214b64; color: #ffffff; outline: 2px solid #9aeaff; outline-offset: 4px; }
button:hover { border-color: #bbf3ff; }
button:focus-visible, .constellation:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
small { font-size: 10px; color: #b5cad8; }
@keyframes flight { 0% { offset-distance: 0%; } 99% { opacity: 1; } 100% { offset-distance: 100%; opacity: 0; } }
@keyframes arrival { 0% { opacity: .8; transform: scale(.5); } 100% { opacity: 0; transform: scale(2); } }
@keyframes highlight { from { opacity: .95; } to { opacity: 0; } }
.message-highlight { animation: highlight 1.6s linear both; }
.message-flight { animation: flight 1.6s linear both; }
.arrival { animation: arrival .7s 1.6s both; }
@media (prefers-reduced-motion: reduce) {
  .message-flight, .arrival, .message-highlight { animation: none; visibility: hidden; }
}
.motion-toggle { position: absolute; right: 12px; top: 12px; z-index: 1; padding: 6px 10px; min-height: 32px; background: #11283a; border: 1px solid #446277; border-radius: 6px; color: #c0d2df; cursor: pointer; font: inherit; font-size: 11px; }
.motion-toggle[aria-pressed=true] { color: #9aeaff; border-color: #73adbf; }
.motion-off .message-flight, .motion-off .arrival, .motion-off .message-highlight { visibility: hidden; }
.mini { aspect-ratio: auto; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; padding: 12px; }
.mini > button:not(.motion-toggle) { position: static; transform: none; min-height: 48px; font-size: 12px; white-space: normal; }
.mini button.selected { outline-offset: 1px; }
.constellation:not(.mini) { min-height: 540px; }
@media (max-width: 760px) {
  .constellation:not(.mini) > button:not(.motion-toggle) { font-size: 12px; padding: 6px; gap: 3px; }
  .constellation:not(.mini) .motion-toggle { top: 4px; right: 4px; font-size: 10px; min-height: 28px; padding: 4px 6px; }
}
.message-flight { offset-anchor: 0px 0px; offset-rotate: 0deg; }
.wire-label { fill: var(--wire-color); stroke: #0a1a2c; stroke-width: 6; paint-order: stroke; text-anchor: middle; dominant-baseline: central; font-size: 22px; font-weight: 700; pointer-events: none; }
.static-arrival { fill: none; stroke: var(--wire-color); stroke-width: 3; pointer-events: none; }
.handoffs { display: grid; gap: 8px; margin-top: 12px; }
.handoffs h3, .arrival-note { margin: 0; }
.handoffs ol { display: grid; gap: 6px; padding: 0; margin: 0; list-style: none; }
.handoffs button, .handoff-detail button { min-height: 36px; padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface); color: var(--text); cursor: pointer; font: inherit; }
.handoffs button { width: 100%; text-align: start; border-inline-start: 4px solid var(--wire-color); }
.handoffs button:hover, .handoff-detail button:hover { background: var(--surface-hover, var(--surface)); border-block-color: var(--accent); border-inline-end-color: var(--accent); }
.handoffs button[data-decision=rollback] { border-inline-start-style: dashed; }
.handoff-detail { width: min(32rem, calc(100vw - 2rem)); max-height: calc(100dvh - 2rem); padding: 20px; color: var(--text); background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); overflow-wrap: anywhere; }
.handoff-detail::backdrop { background: #0006; }
.handoff-detail form { display: flex; justify-content: flex-end; }
.handoff-detail h3 { margin-block: 12px; }
@media (max-width: 760px) { .wire-label { transform-box: fill-box; transform-origin: center; transform: scale(1.6, .77); } }
</style>
