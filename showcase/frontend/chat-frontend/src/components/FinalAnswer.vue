<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { api } from '../api/client'
import { renderSafeMarkdown } from '../renderers/markdown-adapter'
const props = defineProps<{ jobId: string }>()
const answer = ref<Awaited<ReturnType<typeof api.finalAnswer>> | null>(null)
const error = ref('')
const waiting = ref(true)
const labels = { solve: '求解', teach: '教学', report: '报告' }
const boundaries = { ready: '', pending: '正在整理最终答复…', failed: '所选格式生成失败，以下为已有答案。', legacy: '历史结果，保留原有格式。', stale: '结果来源已变化，以下仅为当前可用答案。', unavailable: '当前没有可用答复。' }
const html = computed(() => renderSafeMarkdown(answer.value?.answer ?? ''))
let generation = 0
let timer: ReturnType<typeof setTimeout> | undefined
async function load(id: string, token: number, attempt = 0): Promise<void> {
  if (token !== generation) return
  let retry = false
  try {
    const result = await api.finalAnswer(id)
    if (token !== generation) return
    answer.value = result; error.value = ''; retry = result.presentation_status === 'pending'
  } catch {
    if (token !== generation) return
    retry = true; error.value = '答复尚未就绪，请稍后重新读取。'
  }
  waiting.value = retry && attempt < 90
  if (waiting.value) timer = setTimeout(() => { void load(id, token, attempt + 1) }, 2000)
}
function refresh() { clearTimeout(timer); answer.value = null; error.value = ''; waiting.value = true; void load(props.jobId, ++generation) }
watch(() => props.jobId, refresh, { immediate: true })
onUnmounted(() => { generation++; clearTimeout(timer) })
</script>
<template>
  <section class="report-section" aria-label="最终答复" :aria-busy="waiting">
    <h2>最终答复<span v-if="answer"> · {{ labels[answer.mode] }}</span></h2>
    <p v-if="answer && boundaries[answer.presentation_status]" role="status">{{ boundaries[answer.presentation_status] }}</p>
    <p v-if="answer?.notice">{{ answer.notice }}</p>
    <div v-if="html" class="report-content" v-html="html"></div>
    <p v-if="!answer" role="status">{{ error || '正在读取答复…' }}</p>
    <button v-if="!waiting && (error || answer?.presentation_status === 'pending')" type="button" @click="refresh">重新读取答复</button>
  </section>
</template>
<style scoped>
section { margin-block: var(--space-4); overflow-wrap: anywhere; }
h2 { font-size: var(--text-lg); }
</style>
