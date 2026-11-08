<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '../api/client'
import { renderSafeMarkdown } from '../renderers/markdown-adapter'
import type { PresentationMode, PresentationResponse } from '../api/presentation.schemas'
import StatusBadge from './ui/StatusBadge.vue'
import UiButton from './ui/UiButton.vue'

const props = defineProps<{
  jobId: string
  mode: PresentationMode
  jobStatus: string
  problem?: string
  fallbackAnswer?: string
}>()

const view = ref<'answer' | 'presentation'>('answer')
const response = ref<PresentationResponse | null>(null)
const loading = ref(false)
const loadError = ref('')
let requestGeneration = 0
const modeLabels: Record<string, string> = { solve: '求解', teach: '教学', report: '报告' }
const artifact = computed(() => response.value?.presentation)
const sourceStatus = computed(() => artifact.value?.status === 'needs_review' ? 'needs_review' : artifact.value?.sources.length ? 'current' : 'unknown')
const expressionText = computed(() => artifact.value?.paragraphs.map((item) => item.text).join('\n\n') ?? '')
const renderedAnswer = computed(() => renderSafeMarkdown(response.value?.answer ?? props.fallbackAnswer ?? ''))
const renderedExpression = computed(() => renderSafeMarkdown(expressionText.value))
const completionLabel = computed(() => artifact.value?.completion === 'complete' ? '义务已完成' : artifact.value?.completion === 'partial' ? '部分完成' : '未完成')

watch(() => [props.jobId, props.mode, props.jobStatus] as const, async ([jobId, mode, status]) => {
  const generation = ++requestGeneration
  response.value = null
  loadError.value = ''
  view.value = 'answer'
  if (!['succeeded', 'failed', 'canceled'].includes(status)) return
  loading.value = true
  try {
    const loaded = await api.presentation(jobId, mode)
    if (generation === requestGeneration) response.value = loaded
  } catch (error) {
    if (generation === requestGeneration) {
      loadError.value = error instanceof Error ? error.message : '表达产物暂时不可用。'
    }
  } finally {
    if (generation === requestGeneration) loading.value = false
  }
}, { immediate: true })
</script>

<template>
  <section class="presentation-section" aria-label="S06 输出模式" :data-presentation-mode="mode" :data-artifact-id="artifact?.artifact.id" :data-source-job-id="artifact?.job_id">
    <div class="presentation-heading">
      <div>
        <h2>独立输出 · {{ modeLabels[mode] ?? mode }}</h2>
        <p v-if="problem" class="presentation-problem">题目：{{ problem }}</p>
      </div>
      <div class="review-meta">
        <StatusBadge :value="mode" />
        <StatusBadge v-if="artifact" :value="artifact.status" />
        <StatusBadge v-if="artifact" :value="artifact.completion" />
      </div>
    </div>
    <div class="presentation-tabs" role="group" aria-label="输出内容">
      <UiButton :variant="view === 'answer' ? 'primary' : 'secondary'" :aria-pressed="view === 'answer'" @click="view = 'answer'">原答案</UiButton>
      <UiButton :variant="view === 'presentation' ? 'primary' : 'secondary'" :aria-pressed="view === 'presentation'" @click="view = 'presentation'">表达内容</UiButton>
    </div>
    <p v-if="loading" role="status" aria-busy="true">正在恢复已保存的表达产物…</p>
    <p v-if="loadError" class="notice notice--warning" role="status">{{ loadError }} 原答案仍可查看。</p>
    <article v-if="view === 'answer'" class="presentation-content" aria-label="原答案内容">
      <div class="report-content" v-html="renderedAnswer"></div>
    </article>
    <article v-else-if="artifact" class="presentation-content" aria-label="表达内容">
      <div class="report-content" v-html="renderedExpression"></div>
      <details class="presentation-claims" open>
        <summary>段落证据状态（模板化基础输出）</summary>
        <ul>
          <li v-for="paragraph in artifact.paragraphs" :key="paragraph.id">
            <span>{{ paragraph.kind === 'mathematical' ? '数学段落' : '模板说明' }}：{{ paragraph.status }} · {{ paragraph.grade }}</span>
            <small v-if="paragraph.claim_refs.length">来源 {{ paragraph.claim_refs.join('、') }}</small>
            <small v-else>无当前来源，保持待验证</small>
          </li>
        </ul>
      </details>
    </article>
    <article v-else-if="view === 'presentation'" class="presentation-content" aria-label="表达内容">
      <p>表达产物暂不可用，请稍后重试；原答案保留在“原答案”视图。</p>
    </article>
    <div v-if="artifact" class="presentation-evidence" aria-label="证据状态">
      <h3>证据状态</h3>
      <dl class="data-list">
        <dt>当前来源</dt><dd><StatusBadge :value="sourceStatus" /></dd>
        <dt>验证状态</dt><dd>{{ completionLabel }}；形式化验证：{{ artifact.formal_verification }}</dd>
        <dt>已验证范围</dt><dd>{{ artifact.scope.covered }} / {{ artifact.scope.total }} 项根义务</dd>
        <dt>未完成义务</dt><dd>{{ artifact.scope.unresolved.length ? artifact.scope.unresolved.length + ' 项待处理' : '无' }}</dd>
      </dl>
      <p v-if="artifact.status === 'needs_review'" class="notice notice--warning" role="alert">来源版本已变化，历史表达需要重新审阅；原答案仍保留。</p>
      <p v-else class="presentation-note">teach/report 为模板化基础输出并引用原文，不代表新增讲解质量。相同原文仅沿用当前有效证据；新增数学内容保持待验证。</p>
      <ul v-if="response?.presentation_history.length" class="presentation-history" aria-label="历史表达状态">
        <li v-for="historical in response.presentation_history" :key="historical.artifact.id">
          <StatusBadge :value="historical.status" /> 历史版本 {{ historical.artifact.id }} · {{ historical.revalidation_reason ?? '来源版本变化' }}
        </li>
      </ul>
    </div>
  </section>
</template>
