<script setup lang="ts">
defineProps<{ modelValue: string; modes: Array<{ solver_mode: string; enabled: boolean }>; disabled: boolean }>()
const labels: Record<string, string> = { star_limited: 'STAR 受限', star_limited_best_effort: 'STAR 受限 Best-Effort', star_reference: 'STAR 完整参考', star_best_effort: 'STAR Best-Effort' }
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
</script>

<template>
  <div class="solver-mode">
    <label for="solver-mode">求解模式</label>
    <select id="solver-mode" :value="modelValue" :disabled="disabled" aria-describedby="solver-mode-note" @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)">
      <option value="legacy">原有聊天</option>
      <option v-for="mode in modes.filter(item => item.solver_mode !== 'legacy')" :key="mode.solver_mode" :value="mode.solver_mode" :disabled="!mode.enabled">{{ labels[mode.solver_mode] ?? mode.solver_mode }}{{ mode.enabled ? '' : '（服务未启用）' }}</option>
    </select>
    <p id="solver-mode-note">{{ modelValue.includes('best_effort') ? '显式 Best-Effort：预算终止后仅选择已有候选，不增加模型或工具调用；仍可能未解决。' : modelValue.startsWith('star_') ? '采用服务端声明的 STAR 模式；运行状态与数学验证范围分别审阅。' : '采用服务当前的原有聊天策略；STAR 需显式选择。' }}</p>
  </div>
</template>

<style scoped>
.solver-mode { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); padding: var(--space-3) var(--space-4) 0; }
.solver-mode label { font-weight: 600; }
.solver-mode select { max-width: 100%; min-width: 0; color: var(--text); background: var(--surface); border: 1px solid var(--border-strong); border-radius: var(--radius-sm); padding: var(--space-2); font: inherit; }
.solver-mode p { flex-basis: 100%; margin: 0; color: var(--muted); font-size: .75rem; }
</style>
