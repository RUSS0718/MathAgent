<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { isApiError } from '../api/errors'
import type { JobReport } from '../api/reports.schemas'
import { describeResultSemantics } from '../runtime/reports/result-semantics'
import { buildSystemDeepLink } from '../runtime/navigation/system-deeplink'
import { api } from '../api/client'
import { renderSafeMarkdown } from '../renderers/markdown-adapter'
import type { PresentationMode, PresentationResponse } from '../api/presentation.schemas'
import StatusBadge from './ui/StatusBadge.vue'
import UiButton from './ui/UiButton.vue'

const props = defineProps<{
  jobId: string
  mode?: PresentationMode
  jobStatus: string
  problem?: string
  fallbackAnswer?: string
  sourceVersion?: unknown
  answerReport?: JobReport['report']
}>()

const selectedMode = ref<PresentationMode>(props.mode ?? 'teach')
watch(() => [props.jobId, props.mode], () => { selectedMode.value = props.mode ?? 'teach' })
const systemViewEnabled = import.meta.env.VITE_F7_SYSTEM_VIEW_ENABLED === 'true'
const view = ref<'answer' | 'presentation'>('answer')
const response = ref<PresentationResponse | null>(null)
const loading = ref(false)
const loadError = ref('')
let requestGeneration = 0
const modeLabels: Record<string, string> = { solve: '求解', teach: '教学', report: '报告' }
const providerKnown = computed(() => {
  const value = props.answerReport?.budget?.provider_known
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
})
const artifact = computed(() => response.value?.presentation)
const sourceStatus = computed(() => artifact.value?.status === 'needs_review' ? 'needs_review' : artifact.value?.sources.length ? 'current' : 'unknown')
const renderedAnswer = computed(() => renderSafeMarkdown(response.value?.answer ?? props.fallbackAnswer ?? ''))
const completionLabel = computed(() => artifact.value?.completion === 'complete' ? '义务已完成' : artifact.value?.completion === 'partial' ? '部分完成' : '未完成')
const budgetLabels: Record<string, string> = {
  http_attempts: 'HTTP 请求数', unknown_attempts: '未知请求数',
  reserved_tokens: '未决预留 Token', charged_tokens: '累计计入 Token', deadline_at: '原截止时间',
}

function evidenceId(reference: string): string {
  return `presentation-${props.jobId}-${reference}`
}

function systemHref(paragraphId?: string): string | undefined {
  const current = artifact.value
  if (!systemViewEnabled || !current?.output_request) return undefined
  try {
    return buildSystemDeepLink({ runId: props.jobId, mode: current.mode,
      outputId: current.output_request.id, artifactId: current.artifact.id, paragraphId })
  } catch { return undefined }
}

async function load(generate = false): Promise<void> {
  const generation = ++requestGeneration
  const jobId = props.jobId
  const mode = selectedMode.value
  loadError.value = ''
  loading.value = false
  if (!['succeeded', 'failed', 'canceled'].includes(props.jobStatus)) return
  loading.value = true
  try {
    const loaded = await (generate ? api.presentation(jobId, mode) : api.readPresentation(jobId, mode))
    if (generation === requestGeneration) {
      response.value = loaded
      if (generate) view.value = 'presentation'
    }
  } catch (error) {
    if (generation === requestGeneration) {
      loadError.value = isApiError(error) && error.status === 404 && error.code === 'presentation_unavailable'
        ? '尚未保存此模式的表达，可显式生成模板。'
        : error instanceof Error ? error.message : '表达产物暂时不可用。'
    }
  } finally {
    if (generation === requestGeneration) loading.value = false
  }
}
watch(() => [props.jobId, selectedMode.value, props.jobStatus, props.sourceVersion], () => {
  response.value = null
  view.value = 'answer'
  void load()
}, { immediate: true })
</script>

<template>
  <section class="presentation-section" aria-label="S06 输出模式" :data-presentation-mode="selectedMode" :data-artifact-id="artifact?.artifact.id" :data-source-job-id="artifact?.job_id">
    <div class="presentation-heading">
      <div>
        <h2>独立输出 · {{ modeLabels[selectedMode] ?? selectedMode }}</h2>
        <p v-if="problem" class="presentation-problem">题目：{{ problem }}</p>
      </div>
      <div class="review-meta">
        <StatusBadge :value="selectedMode" />
        <StatusBadge v-if="artifact" :value="artifact.status" />
        <StatusBadge v-if="artifact" :value="artifact.completion" />
      </div>
    </div>
    <div class="presentation-tabs" role="group" aria-label="按需表达">
      <label v-if="!props.mode">表达模式
        <select v-model="selectedMode" :disabled="loading" aria-label="表达模式">
          <option value="teach">教学</option><option value="report">报告</option>
        </select>
      </label>
      <UiButton :disabled="loading || !['succeeded', 'failed', 'canceled'].includes(jobStatus)" @click="load(true)">生成模板{{ modeLabels[selectedMode] }}</UiButton>
      <a v-if="systemHref()" :href="systemHref()">查看版本化输出证据</a>
    </div>
    <p class="presentation-note">实验性模板整理：复用已有答案与证据，不是模型新讲解，不升级证明等级。</p>
    <dl class="data-list" aria-label="答案验证边界">
      <dt>验证方式</dt><dd>{{ answerReport?.checks?.checker ?? '未知 / 未记录' }}</dd>
      <dt>验证范围</dt><dd>{{ answerReport?.checks?.scope ?? '未知 / 未记录' }}</dd>
      <dt>要求满足</dt><dd>{{ answerReport?.semantics ? describeResultSemantics(answerReport.semantics) : '未知 / 未记录；任务完成不等于验证要求满足' }}</dd>
      <template v-for="field in ['prompt_tokens', 'completion_tokens', 'total_tokens']" :key="field">
        <dt>Provider {{ field }}</dt><dd>{{ providerKnown[field] ?? '未知 / 未记录' }}</dd>
      </template>
    </dl>
    <div class="presentation-tabs" role="group" aria-label="输出内容">
      <UiButton :variant="view === 'answer' ? 'primary' : 'secondary'" :aria-pressed="view === 'answer'" @click="view = 'answer'">原答案</UiButton>
      <UiButton :variant="view === 'presentation' ? 'primary' : 'secondary'" :aria-pressed="view === 'presentation'" @click="view = 'presentation'">表达内容</UiButton>
    </div>
    <p v-if="loading" role="status" aria-busy="true">正在恢复已保存的表达产物…</p>
    <p v-if="loadError" class="notice notice--warning" role="status">{{ loadError }} 原答案仍可查看。</p>
    <p v-if="artifact?.status === 'failed'" class="notice notice--warning" role="status">表达整理失败，原答案仍可查看。</p>
    <article v-if="view === 'answer'" class="presentation-content" aria-label="原答案内容">
      <div class="report-content" v-html="renderedAnswer"></div>
    </article>
    <article v-else-if="artifact" class="presentation-content" aria-label="表达内容">
      <section v-for="paragraph in artifact.paragraphs" :key="paragraph.id" class="presentation-paragraph">
        <div class="report-content" v-html="renderSafeMarkdown(paragraph.text)"></div>
        <a v-if="systemHref(paragraph.id)" :href="systemHref(paragraph.id)">段落版本与证据</a>
        <details v-if="paragraph.kind === 'mathematical' || paragraph.claim_refs.length" class="presentation-claims" open>
          <summary>段落依据 · {{ paragraph.status }} · {{ paragraph.grade }}</summary>
          <ul v-if="paragraph.claim_refs.length">
            <li v-for="reference in paragraph.claim_refs" :key="reference">
              <a :href="`#${encodeURIComponent(evidenceId(reference))}`">{{ reference }}</a>
            </li>
          </ul>
          <p v-else>无当前来源，保持待验证。</p>
        </details>
      </section>
    </article>
    <article v-else-if="view === 'presentation'" class="presentation-content" aria-label="表达内容">
      <p>尚未保存或表达产物不可用，可显式生成模板；原答案保留在“原答案”视图。</p>
    </article>
    <div v-if="artifact" class="presentation-evidence" aria-label="证据状态">
      <h3>证据状态</h3>
      <dl class="data-list">
        <dt>当前来源</dt><dd><StatusBadge :value="sourceStatus" /></dd>
        <dt>验证状态</dt><dd>{{ completionLabel }}；原答案文字形式化绑定：{{ artifact.formal_verification }}</dd>
        <dt>已验证范围</dt><dd>{{ artifact.scope.covered }} / {{ artifact.scope.total }} 项根义务</dd>
        <dt>未完成义务</dt><dd>{{ artifact.scope.unresolved.length ? artifact.scope.unresolved.length + ' 项待处理' : '无' }}</dd>
      </dl>
      <p v-if="artifact.status === 'needs_review'" class="notice notice--warning" role="alert">来源版本已变化，历史表达需要重新审阅；原答案仍保留。</p>
      <p v-else class="presentation-note">表达整理保留原答案的验证范围；新增数学内容保持待验证。讲解质量需独立评测。</p>
      <section v-if="artifact.delivery" aria-label="同快照交付">
        <h3>本次交付</h3>
        <dl class="data-list">
          <dt>原答案审查等级</dt><dd>{{ artifact.delivery.grade }}</dd>
          <dt>候选选择</dt><dd>{{ artifact.delivery.selection?.status ?? '未启用 Best-Effort' }}</dd>
          <dt>Verified Claims</dt><dd>{{ artifact.delivery.verified_claims.length }} 项可引用断言</dd>
          <dt>Unresolved Goals</dt><dd>{{ artifact.delivery.unresolved_goals.length }} 项未完成义务</dd>
          <template v-for="(label, field) in budgetLabels" :key="field">
            <dt>{{ label }}</dt><dd>{{ field === 'deadline_at' && typeof artifact.delivery.budget?.[field] === 'number' ? new Date(Number(artifact.delivery.budget[field]) * 1000).toLocaleString() : artifact.delivery.budget?.[field] ?? '未知 / 未记录' }}</dd>
          </template>
        </dl>
        <p v-if="artifact.delivery.selection?.status === 'no_eligible_candidate'">没有合格候选，当前交付未完成。</p>
        <ul v-if="artifact.delivery.verified_claims.length">
          <li v-for="claim in artifact.delivery.verified_claims" :key="claim.id">{{ claim.text }} · {{ claim.grade }}</li>
        </ul>
      </section>
      <section v-if="artifact.sources.length" aria-label="段落来源">
        <h3>段落来源</h3>
        <ul>
          <li v-for="source in artifact.sources" :id="evidenceId(source.id)" :key="source.id" tabindex="-1">
            <strong>{{ source.kind ?? 'VerificationRecord' }}</strong> · {{ source.id }}
            <p>{{ source.status }} · {{ source.grade }} · 范围 {{ source.scope }}</p>
            <p v-if="source.graph_version !== undefined">证明图版本 {{ source.graph_version }}</p>
            <p v-if="source.conclusion">推理结论 {{ source.conclusion }}；AND 前提：{{ source.dependencies?.join('、') || '无图内前提' }}</p>
            <p v-if="source.specification_version !== undefined">规格版本 {{ source.specification_version }}</p>
            <p v-if="source.target_hash">形式目标 {{ source.target_hash }}</p>
            <p v-if="source.proof_hash">证明身份 {{ source.proof_hash }}</p>
          </li>
        </ul>
      </section>
      <ul v-if="response?.presentation_history.length" class="presentation-history" aria-label="历史表达状态">
        <li v-for="historical in response.presentation_history" :key="historical.artifact.id">
          <StatusBadge :value="historical.status" /> 历史版本 {{ historical.artifact.id }} · {{ historical.revalidation_reason ?? '来源版本变化' }}
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.presentation-evidence li,
.presentation-claims a {
  overflow-wrap: anywhere;
}

.presentation-evidence li:target {
  outline: 2px solid var(--accent);
  outline-offset: 4px;
}
</style>
