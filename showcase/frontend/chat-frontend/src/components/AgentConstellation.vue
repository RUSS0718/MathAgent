<script setup lang="ts">
import { roles } from '../runtime/jobs/workbench'
import type { Collaboration } from '../api/workbench.schemas'
import { roleLabels } from '../runtime/jobs/causal-progress'
const stateLabels: Record<string, string> = { idle: '未参与', running: '执行中', completed: '已完成', failed: '遇到问题', unknown: '结果未知' }
defineProps<{ selected: string; roleStates: Record<string, string>; messages: Collaboration[]; mini?: boolean }>()
const emit = defineEmits<{ select: [role: string] }>()
function point(role: string) { return roles.find(item => item[0] === role) }
</script>

<template>
  <div class="constellation" tabindex="-1" :class="{ mini }" :aria-label="mini ? '迷你星图角色成果' : '智能体协作星图'">
    <svg viewBox="0 0 1000 700" aria-hidden="true">
      <line v-for="role in roles.slice(1)" :key="role[0]" x1="500" y1="306" :x2="role[2]" :y2="role[3]" />
      <template v-for="message in messages.filter(m => point(m.from_role) && point(m.to_role) && m.from_role !== m.to_role)" :key="message.message_id">
        <path :id="`${mini ? 'mini' : 'full'}-${message.message_id}`" :d="`M ${point(message.from_role)![2]} ${point(message.from_role)![3]} L ${point(message.to_role)![2]} ${point(message.to_role)![3]}`" class="message-wire" />
        <circle r="7" class="message-flight">
          <animateMotion dur="1.4s" repeatCount="1" fill="freeze"><mpath :href="`#${mini ? 'mini' : 'full'}-${message.message_id}`" /></animateMotion>
        </circle>
      </template>
    </svg>
    <button v-for="role in roles" :key="role[0]" type="button" :style="{ left: `${role[2] / 10}%`, top: `${role[3] / 7}%` }"
      :class="[roleStates[role[0]], { selected: selected === role[0] }]" :data-role-state="roleStates[role[0]]" :aria-pressed="selected === role[0]"
      :aria-label="`查看${roleLabels[role[0]]} ${stateLabels[roleStates[role[0]] ?? 'idle'] ?? '状态待确认'}阶段成果`" @click="emit('select', role[0])"><span>{{ roleLabels[role[0]] }}</span><small>{{ stateLabels[roleStates[role[0]] ?? 'idle'] ?? '状态待确认' }}</small></button>
  </div>
</template>

<style scoped>
.constellation { position: relative; aspect-ratio: 1000 / 700; width: 100%; background: radial-gradient(ellipse at center, var(--accent-wash), transparent 70%); }
svg { position: absolute; width: 100%; height: 100%; overflow: visible; }
line { stroke: var(--border-strong); stroke-dasharray: 3 5; }
.message-wire { fill: none; stroke: var(--accent); stroke-width: 2; }
.message-flight { fill: var(--accent); animation: fade-message 1.4s forwards; }
button { position: absolute; transform: translate(-50%, -50%); display: grid; gap: 4px; min-height: 40px; padding: 8px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface); color: var(--muted); cursor: pointer; font: inherit; white-space: nowrap; }
button.running { border-color: var(--accent); color: var(--text); background: var(--accent-wash); }
button.completed { border-color: var(--success); color: var(--success); }
button.failed, button.unknown { border-color: var(--danger); color: var(--danger); }
button.selected { background: var(--accent-wash); outline: 2px solid var(--accent); }
button:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
.constellation:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
small { font-size: 10px; color: var(--muted); }
.mini button { font-size: 10px; min-height: 30px; padding: 4px; }
@keyframes fade-message { 99% { opacity: 1; } 100% { opacity: 0; } }
@media (prefers-reduced-motion: reduce) { .message-flight { display: none; } }
</style>
