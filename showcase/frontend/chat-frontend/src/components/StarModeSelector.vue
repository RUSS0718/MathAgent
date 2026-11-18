<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ modelValue: string; modes: Array<{ solver_mode: string; enabled: boolean }>; disabled: boolean; autonomousMode?: string }>()
const labels: Record<string, string> = { star_limited: '有限预算求解', star_limited_best_effort: '有限预算 · 保留候选', star_reference: '完整参考求解', star_best_effort: '保留已有候选', star_population: '多路线并发求解' }
const groups = computed(() => {
  const modes = [{ solver_mode: 'legacy', enabled: true }, ...props.modes.filter(mode => mode.solver_mode !== 'legacy')]
  return [
    { label: '自主调度', modes: modes.filter(mode => mode.solver_mode === props.autonomousMode) },
    { label: '资源与候选交付', modes: modes.filter(mode => mode.solver_mode !== props.autonomousMode && !['legacy', 'star_population'].includes(mode.solver_mode)) },
    { label: '调试与兼容', modes: modes.filter(mode => mode.solver_mode !== props.autonomousMode && ['legacy', 'star_population'].includes(mode.solver_mode)) },
  ].filter(group => group.modes.length)
})
const note = computed(() => {
  if (props.autonomousMode && props.modelValue === props.autonomousMode) return '由智能体按反馈选择求解路线；配置和资源允许时，可自主使用串行或多路线，无需先判断题目难度。'
  if (props.modelValue === 'star_population') return props.autonomousMode
    ? '显式并发执行预设，用于调试；自主入口也可按需选择多路线。多个不同前沿共享同一 Run，答案交付与请求结算分别记录。'
    : '显式并发路线模式：多个不同前沿可在同一 Run 内并行推进；答案交付与请求结算分别记录。'
  if (props.modelValue.includes('best_effort')) return '保留候选预设：预算终止后仅选择已有候选，不增加模型或工具调用；仍可能未解决。'
  if (props.modelValue === 'star_limited') return '采用服务端配置的有限预算预设；这不是题目难度判断，也不会自动提高根预算。'
  return props.modelValue.startsWith('star_') ? '采用服务端启用的求解模式；运行状态与数学验证范围分别审阅。' : '采用服务当前的原有聊天策略；其他模式需手动选择。'
})
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
</script>

<template>
  <div class="solver-mode">
    <label for="solver-mode">{{ autonomousMode ? '执行预设' : '求解模式' }}</label>
    <select id="solver-mode" name="solver_mode" :value="modelValue" :disabled="disabled" aria-describedby="solver-mode-note" @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)">
      <template v-if="autonomousMode">
        <optgroup v-for="group in groups" :key="group.label" :label="group.label">
          <option v-for="mode in group.modes" :key="mode.solver_mode" :value="mode.solver_mode" :disabled="!mode.enabled">{{ mode.solver_mode === autonomousMode ? '自主求解（推荐）' : mode.solver_mode === 'star_population' ? '多路线并发（调试）' : mode.solver_mode === 'legacy' ? '基础求解（兼容）' : labels[mode.solver_mode] ?? mode.solver_mode }}{{ mode.enabled ? '' : '（服务未启用）' }}</option>
        </optgroup>
      </template>
      <template v-else>
        <option value="legacy">基础求解</option>
        <option v-for="mode in modes.filter(item => item.solver_mode !== 'legacy')" :key="mode.solver_mode" :value="mode.solver_mode" :disabled="!mode.enabled">{{ labels[mode.solver_mode] ?? mode.solver_mode }}{{ mode.enabled ? '' : '（服务未启用）' }}</option>
      </template>
    </select>
    <p id="solver-mode-note">{{ note }}</p>
  </div>
</template>

<style scoped>
.solver-mode { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); padding: var(--space-3) var(--space-4) 0; }
.solver-mode label { font-weight: 600; }
.solver-mode select { max-width: 100%; min-width: 0; color: var(--text); background: var(--surface); border: 1px solid var(--border-strong); border-radius: var(--radius-sm); padding: var(--space-2); font: inherit; }
.solver-mode p { flex-basis: 100%; margin: 0; color: var(--muted); font-size: .75rem; }
</style>
