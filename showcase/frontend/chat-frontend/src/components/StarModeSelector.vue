<script setup lang="ts">
defineProps<{ modelValue: string; modes: Array<{ solver_mode: string; enabled: boolean }>; disabled: boolean }>()
const labels: Record<string, string> = { star_limited: '有限预算求解', star_limited_best_effort: '有限预算 · 保留候选', star_reference: '完整参考求解', star_best_effort: '保留已有候选', star_population: '多路线并发求解' }
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
</script>

<template>
  <div class="solver-mode">
    <label for="solver-mode">求解模式</label>
    <select id="solver-mode" :value="modelValue" :disabled="disabled" aria-describedby="solver-mode-note" @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)">
      <option value="legacy">基础求解</option>
      <option v-for="mode in modes.filter(item => item.solver_mode !== 'legacy')" :key="mode.solver_mode" :value="mode.solver_mode" :disabled="!mode.enabled">{{ labels[mode.solver_mode] ?? mode.solver_mode }}{{ mode.enabled ? '' : '（服务未启用）' }}</option>
    </select>
    <p id="solver-mode-note">{{ modelValue === 'star_population' ? '显式并发路线模式：多个不同前沿可在同一 Run 内并行推进；答案交付与请求结算分别记录。' : modelValue.includes('best_effort') ? '保留候选模式：预算终止后仅选择已有候选，不增加模型或工具调用；仍可能未解决。' : modelValue.startsWith('star_') ? '采用服务端启用的求解模式；运行状态与数学验证范围分别审阅。' : '采用服务当前的原有聊天策略；其他模式需手动选择。' }}</p>
  </div>
</template>

<style scoped>
.solver-mode { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); padding: var(--space-3) var(--space-4) 0; }
.solver-mode label { font-weight: 600; }
.solver-mode select { max-width: 100%; min-width: 0; color: var(--text); background: var(--surface); border: 1px solid var(--border-strong); border-radius: var(--radius-sm); padding: var(--space-2); font: inherit; }
.solver-mode p { flex-basis: 100%; margin: 0; color: var(--muted); font-size: .75rem; }
</style>
