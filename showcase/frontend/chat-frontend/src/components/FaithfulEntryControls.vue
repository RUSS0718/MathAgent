<script setup lang="ts">
/** Product entry follows service readiness; technical modes stay explicit. */
import { computed } from 'vue'
import type { CapabilitiesResponse } from '../api/capabilities.schemas'
import StarModeSelector from './StarModeSelector.vue'
import UiButton from './ui/UiButton.vue'

const props = defineProps<{
  faithful: NonNullable<CapabilitiesResponse['faithful']>
  modelValue: string
  modes: Array<{ solver_mode: string; enabled: boolean }>
  disabled: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const modes = computed(() => [
  { solver_mode: props.faithful.solver_mode, enabled: props.faithful.ready },
  ...props.modes.filter(mode => mode.solver_mode !== props.faithful.solver_mode),
])
</script>

<template>
  <div class="faithful-entry">
    <p>实验性能力 · 根据当前任务的配置与准入条件使用；不代表数学效果已验收。</p>
    <p v-if="faithful.optional_limitations?.length">可选能力限制：{{ faithful.optional_limitations.join('；') }}</p>
    <p v-if="!faithful.ready" role="alert">Faithful 尚未就绪，暂不能提交。{{ faithful.unavailable_reasons.join('；') || '服务未提供缺失原因，请检查服务配置。' }}</p>
    <p v-else role="status">{{ modelValue === faithful.solver_mode ? 'Faithful 自主求解：根据题目自主选择已配置能力；简单题可直接完成。' : '已手选高级求解模式。' }}</p>
    <details>
      <summary>高级选项</summary>
      <UiButton v-if="modelValue !== faithful.solver_mode" :disabled="disabled || !faithful.ready" @click="emit('update:modelValue', faithful.solver_mode)">使用 Faithful 自主求解</UiButton>
      <StarModeSelector :model-value="modelValue" :modes="modes" :disabled="disabled || !faithful.ready" @update:model-value="emit('update:modelValue', $event)" />
    </details>
  </div>
</template>

<style scoped>
.faithful-entry { padding: var(--space-3) var(--space-4) 0; color: var(--muted); font-size: .875rem; overflow-wrap: anywhere; }
.faithful-entry p { margin: 0 0 var(--space-2); }
.faithful-entry summary { cursor: pointer; color: var(--text); }
</style>
