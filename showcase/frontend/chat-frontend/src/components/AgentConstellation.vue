<script setup lang="ts">
import { roles } from '../runtime/jobs/workbench'
import type { Collaboration } from '../api/workbench.schemas'
defineProps<{ selected: string; activeRoles: string[]; message: Collaboration | null; mini?: boolean }>()
const emit = defineEmits<{ select: [role: string] }>()
function point(role: string) { return roles.find(item => item[0] === role) ?? roles[0] }
</script>

<template>
  <div class="constellation" :class="{ mini }" :aria-label="mini ? '迷你星图角色筛选' : '智能体协作星图'">
    <svg viewBox="0 0 1000 620" aria-hidden="true">
      <line v-for="role in roles.slice(1)" :key="role[0]" x1="500" y1="306" :x2="role[2]" :y2="role[3]" />
      <template v-if="message">
        <path :id="`${mini ? 'mini' : 'full'}-message-path`" :d="`M ${point(message.from_role)[2]} ${point(message.from_role)[3]} L ${point(message.to_role)[2]} ${point(message.to_role)[3]}`" class="message-wire" />
        <circle :key="message.message_id" r="7" class="message-flight">
          <animateMotion dur="1.4s" repeatCount="1" fill="freeze"><mpath :href="`#${mini ? 'mini' : 'full'}-message-path`" /></animateMotion>
        </circle>
      </template>
    </svg>
    <button v-for="role in roles" :key="role[0]" type="button" :style="{ left: `${role[2] / 10}%`, top: `${role[3] / 6.2}%` }"
      :class="{ visited: activeRoles.includes(role[0]), selected: selected === role[0] }" :aria-pressed="selected === role[0]"
      :aria-label="`筛选${role[1]}角色`" @click="emit('select', role[0])"><span>{{ role[1] }}</span><small v-if="!mini">{{ activeRoles.includes(role[0]) ? '有持久事件' : '暂无事件' }}</small></button>
  </div>
</template>

<style scoped>
.constellation { position: relative; aspect-ratio: 1000 / 620; width: 100%; background: radial-gradient(ellipse at center, var(--accent-wash), transparent 70%); }
svg { position: absolute; width: 100%; height: 100%; overflow: visible; }
line { stroke: var(--border-strong); stroke-dasharray: 3 5; }
.message-wire { fill: none; stroke: var(--accent); stroke-width: 2; }
.message-flight { fill: var(--accent); animation: fade-message 1.4s forwards; }
button { position: absolute; transform: translate(-50%, -50%); display: grid; gap: 4px; min-height: 40px; padding: 8px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface); color: var(--muted); cursor: pointer; font: inherit; white-space: nowrap; }
button.visited { border-color: var(--accent); color: var(--text); }
button.selected { background: var(--accent-wash); outline: 2px solid var(--accent); }
button:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
small { font-size: 10px; color: var(--muted); }
.mini button { font-size: 10px; min-height: 30px; padding: 4px; }
@keyframes fade-message { 99% { opacity: 1; } 100% { opacity: 0; } }
@media (prefers-reduced-motion: reduce) { .message-flight { display: none; } }
</style>
