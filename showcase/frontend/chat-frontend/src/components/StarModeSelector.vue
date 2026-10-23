<script setup lang="ts">
defineProps<{ modelValue: string; enabled: boolean; disabled: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
</script>

<template>
  <div class="solver-mode">
    <label for="solver-mode">求解模式</label>
    <select id="solver-mode" :value="modelValue" :disabled="disabled" aria-describedby="solver-mode-note" @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)">
      <option value="legacy">原有聊天</option>
      <option value="star_limited" :disabled="!enabled">STAR 受限{{ enabled ? '' : '（服务未启用）' }}</option>
      <option disabled>STAR 完整参考（前置验收未通过）</option>
      <option disabled>STAR Best-Effort（前置验收未通过）</option>
    </select>
    <p id="solver-mode-note">{{ modelValue === 'star_limited' ? '探索 → 润色 → 新整题审查；隔离 Python、安全续算与完整机制尚未验收。' : '采用服务当前的原有聊天策略；STAR 需显式选择。' }}</p>
  </div>
</template>

<style scoped>
.solver-mode { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); padding: var(--space-3) var(--space-4) 0; }
.solver-mode label { font-weight: 600; }
.solver-mode select { max-width: 100%; min-width: 0; color: var(--text); background: var(--surface); border: 1px solid var(--border-strong); border-radius: var(--radius-sm); padding: var(--space-2); font: inherit; }
.solver-mode p { flex-basis: 100%; margin: 0; color: var(--muted); font-size: .75rem; }
</style>
