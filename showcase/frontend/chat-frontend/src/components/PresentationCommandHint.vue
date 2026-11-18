<script setup lang="ts">
defineProps<{ enabled: boolean }>()
</script>

<template>
  <p class="presentation-command-hint" :data-enabled="enabled">
    <template v-if="enabled">输出模式：在题目前输入 /solve、/teach 或 /report；普通提交保持原有行为。teach/report 使用模板与原文引用。</template>
    <template v-else>输出模式当前不可用；普通提交保持原有行为。</template>
  </p>
</template>

<style scoped>
.presentation-command-hint { flex-basis: 100%; margin: 0; padding: 0 var(--space-4); color: var(--muted); font-size: var(--text-xs); }
</style>
