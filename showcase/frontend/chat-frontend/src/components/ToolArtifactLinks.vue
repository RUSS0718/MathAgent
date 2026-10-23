<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ jobId: string; receipt: unknown }>()
const refs = computed(() => {
  if (!props.receipt || typeof props.receipt !== 'object') return []
  const receipt = props.receipt as Record<string, unknown>
  return ['code_ref', 'input_ref', 'stdout_ref', 'stderr_ref', 'receipt_ref'].flatMap(key => {
    const ref = receipt[key]
    if (!ref || typeof ref !== 'object') return []
    const value = ref as Record<string, unknown>
    return value.run_id === props.jobId && typeof value.sha256 === 'string' && /^[0-9a-f]{64}$/.test(value.sha256)
      ? [{ key, hash: value.sha256, size: value.size }] : []
  })
})
</script>
<template>
  <ul v-if="refs.length"><li v-for="ref in refs" :key="ref.key"><a :href="`/api/agent/jobs/${encodeURIComponent(jobId)}/artifacts/${ref.hash}`" target="_blank" rel="noopener">{{ ref.key }} · {{ ref.hash }} · {{ ref.size }} bytes</a></li></ul>
  <p v-else>无可解析的内容寻址产物；普通引用不代表已保存执行内容。</p>
</template>
