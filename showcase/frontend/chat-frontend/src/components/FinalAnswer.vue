<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { api } from '../api/client'
import { downloadReport } from '../../../deeptutor-preview/lib/report-export'
import { renderSafeMarkdown } from '../renderers/markdown-adapter'
const props = defineProps<{ jobId: string; status?: string; source: string }>()
const answer = ref<Awaited<ReturnType<typeof api.finalAnswer>> | null>(null)
const error = ref('')
const waiting = ref(true)
const labels = { solve: '求解', teach: '教学', report: '报告' }
const mode = computed(() => answer.value?.presentation_status === 'ready' ? answer.value.mode : undefined)
const statusLabel = computed(() => answer.value ? {
  ready: '已就绪', pending: '整理中', failed: '格式生成失败', legacy: '原有格式', stale: '来源已变化', unavailable: '格式不可用',
}[answer.value.presentation_status] : '')
const provenance = computed(() => `来源：${props.source} · 答复状态：${statusLabel.value}`)
const copyNotice = ref('')
const markdown = computed(() => ['# 求解报告', provenance.value, answer.value?.notice, content.value].filter(Boolean).join('\n\n'))
async function copyReport() {
  try { await navigator.clipboard.writeText(markdown.value); copyNotice.value = '报告已复制' }
  catch { copyNotice.value = '无法访问剪贴板，请使用导出 Markdown。' }
}
const boundaries = { ready: '', pending: '正在整理最终答复…', failed: '所选格式生成失败，以下为已有答案。', legacy: '历史结果，保留原有格式。', stale: '结果来源已变化，以下仅为当前可用答案。', unavailable: '当前答复格式暂不可用。' }
const content = computed(() => {
  const text = answer.value?.answer ?? ''
  return !text.trim() || text.trim() === 'No complete answer is available for this run.' ? '' : text
})
const partial = computed(() => !!content.value && answer.value?.status !== 'succeeded')
const exportable = computed(() => mode.value === 'report' && !!content.value && !partial.value)
const title = computed(() => {
  if (!answer.value) return '答复状态'
  if (content.value) return partial.value ? '部分结果' : '最终答复'
  if (answer.value.presentation_status === 'pending') return '正在整理答复'
  return answer.value.status === 'unknown' ? '结果状态待确认' : '未生成答案'
})
const availability = computed(() => {
  if (partial.value) return '本次求解尚未成功完成，以下仅为已保存的部分结果。'
  if (!answer.value || content.value || answer.value.presentation_status === 'pending') return ''
  return answer.value.status === 'unknown' ? '本次运行的结果尚无法确认，当前没有可用答案。' : '本次运行没有可用答复。'
})
const html = computed(() => renderSafeMarkdown(content.value))
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
function refresh() { clearTimeout(timer); answer.value = null; error.value = ''; copyNotice.value = ''; waiting.value = true; void load(props.jobId, ++generation) }
watch(() => [props.jobId, props.status], refresh, { immediate: true })
onUnmounted(() => { generation++; clearTimeout(timer) })
</script>
<template>
  <section class="report-section" aria-label="最终答复" :aria-busy="waiting">
    <h2>{{ title }}<span v-if="mode"> · {{ labels[mode] }}</span></h2>
    <small v-if="answer">{{ provenance }}</small>
    <p v-if="availability" role="status">{{ availability }}</p>
    <p v-if="answer && (content || (!answer.notice && answer.presentation_status === 'pending')) && boundaries[answer.presentation_status]" role="status">{{ boundaries[answer.presentation_status] }}</p>
    <p v-if="answer?.notice">{{ answer.notice }}</p>
    <div v-if="exportable" class="report-actions" aria-label="报告操作">
      <button type="button" @click="copyReport">复制报告</button>
      <button type="button" @click="downloadReport('求解报告', markdown)">导出 Markdown</button>
      <small role="status">{{ copyNotice }}</small>
    </div>
    <div v-if="html" class="report-content" v-html="html"></div>
    <p v-if="!answer" role="status">{{ error || '正在读取答复…' }}</p>
    <button v-if="!waiting && (error || answer?.presentation_status === 'pending')" type="button" @click="refresh">重新读取答复</button>
  </section>
</template>
<style scoped>
section { margin-block: var(--space-4); overflow-wrap: anywhere; }
h2 { font-size: var(--text-lg); }
</style>
