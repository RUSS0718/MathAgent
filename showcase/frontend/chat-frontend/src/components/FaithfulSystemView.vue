<script setup lang="ts">
/** Read-only Run/evidence browser restored entirely from the v1 URL state. */
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api/client'
import type { SystemRunResponse, SystemRunSummary } from '../api/system.schemas'
import PageFrame from './ui/PageFrame.vue'
import FaithfulDependencyGraph from './FaithfulDependencyGraph.vue'
import { buildSystemDeepLink, parseSystemDeepLink, type SystemDeepLinkState } from '../runtime/navigation/system-deeplink'

const route = ref(parseSystemDeepLink(globalThis.location.pathname, globalThis.location.search))
const list = ref<SystemRunSummary[]>([])
const total = ref(0)
const detail = ref<SystemRunResponse | null>(null)
const loading = ref(false)
const error = ref('')
let loadGeneration = 0
let loadedLocation = ''
const selected = computed(() => route.value.kind === 'valid' ? route.value.state : null)
const selectedPresentation = computed(() => detail.value?.selection.presentation ?? null)

function runHref(run: SystemRunSummary): string {
  return buildSystemDeepLink({ runId: run.run_id, mode: (run.presentation_mode ?? 'solve') as SystemDeepLinkState['mode'] })
}

function paragraphHref(paragraphId: string): string {
  const state = selected.value
  const presentation = selectedPresentation.value
  if (!state || !presentation?.output_request?.id || !presentation.artifact?.id) return '#'
  return buildSystemDeepLink({ ...state, outputId: presentation.output_request.id,
    artifactId: presentation.artifact.id, paragraphId })
}

function outputHref(output: SystemRunResponse['presentations'][number]): string {
  return buildSystemDeepLink({ runId: detail.value!.run.run_id, mode: output.mode,
    outputId: output.output_id, artifactId: output.artifact_id })
}

function nodeHref(nodeId: string): string {
  const state = selected.value
  const graph = detail.value?.graph
  if (!state || !graph) return '#'
  return buildSystemDeepLink({ ...state, graphVersion: graph.graph_version, nodeId })
}

function sourceHref(nodeId: string, graphVersion: number): string {
  return buildSystemDeepLink({ ...selected.value!, graphVersion, nodeId })
}

async function load(): Promise<void> {
  loadedLocation = globalThis.location.pathname + globalThis.location.search
  const generation = ++loadGeneration
  route.value = parseSystemDeepLink(globalThis.location.pathname, globalThis.location.search)
  const requested = route.value
  loading.value = true
  error.value = ''
  detail.value = null
  try {
    if (requested.kind === 'list') {
      const response = await api.faithfulRuns()
      if (generation !== loadGeneration) return
      list.value = response.items
      total.value = response.total
    } else if (requested.kind === 'valid') {
      const response = await api.faithfulRun(requested.state)
      if (generation !== loadGeneration) return
      detail.value = response
      if (requested.state.paragraphId || requested.state.nodeId) {
        await nextTick()
        if (generation !== loadGeneration) return
        const target = requested.state.paragraphId
          ? `f7-${requested.state.paragraphId.replace(':', '-')}`
          : `f7-node-${encodeURIComponent(requested.state.nodeId!)}`
        document.getElementById(target)?.scrollIntoView({ block: 'center' })
      }
    } else if (requested.kind === 'invalid') {
      error.value = `深链不可用：${requested.reason}`
    } else {
      error.value = '此地址不是 F7 系统视图。'
    }
  } catch (cause) {
    if (generation !== loadGeneration) return
    error.value = cause instanceof Error ? cause.message : '只读系统视图暂不可用。'
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

function onPopState(): void {
  if (loadedLocation !== globalThis.location.pathname + globalThis.location.search) void load()
}
onMounted(() => { void load(); globalThis.addEventListener('popstate', onPopState) })
onUnmounted(() => { loadGeneration += 1; globalThis.removeEventListener('popstate', onPopState) })
</script>

<template>
  <PageFrame title="Faithful 系统视图" description="只读浏览持久化 Run、依赖图与 F6 交付证据。" active="system">
    <div class="f7-toolbar"><a href="/dashboard">返回数学工作区</a><a href="/dashboard/system">Run 列表</a></div>
    <p v-if="loading" role="status" aria-busy="true">正在读取持久化公开数据…</p>
    <p v-if="error" class="notice notice--warning" role="alert">{{ error }}</p>
    <p v-if="route.kind === 'valid' && route.unavailableReason" class="notice notice--warning" role="status">
      输出身份不完整（{{ route.unavailableReason }}）；已保留当前 Run，输出 unavailable。
    </p>
    <template v-if="route.kind === 'list' && !loading && !error">
      <p class="muted">共 {{ total }} 个持久化 Run。此页面只读取已保存数据。</p>
      <ul class="f7-run-list">
        <li v-for="run in list" :key="run.run_id">
          <a :href="runHref(run)">{{ run.run_id }}</a>
          <span>{{ run.status }}</span><span>{{ run.presentation_mode ?? '无 F6 输出模式' }}</span>
          <time>{{ run.updated_at ?? run.created_at ?? '时间未记录' }}</time>
        </li>
      </ul>
      <p v-if="!list.length" class="empty-state">当前没有可见的持久化 Run。</p>
    </template>
    <template v-if="detail && selected">
      <section class="evidence-section" aria-label="Run 摘要">
        <h2>{{ detail.run.run_id }}</h2>
        <p>{{ detail.run.status }} · {{ detail.run.execution_mode ?? 'execution mode 未记录' }} · {{ detail.run.solver_mode ?? 'solver mode 未记录' }}</p>
      </section>
      <section class="evidence-section" aria-label="已保存输出">
        <h2>已保存输出</h2>
        <ul class="f7-sources">
          <li v-for="output in detail.presentations" :key="output.artifact_id">
            <a :href="outputHref(output)">{{ output.mode }} · {{ output.artifact_id }}</a>
          </li>
        </ul>
        <p v-if="!detail.presentations.length">此 Run 没有已保存的 F6 输出。</p>
      </section>
      <p v-if="detail.selection.status === 'unavailable'" class="notice notice--warning" role="status">
        {{ selected.outputId ? '指定的 F6 输出身份不存在；已保留当前 Run。' : '请选择具有独立身份的已保存输出。' }}
      </p>
      <p v-else-if="detail.selection.paragraph_status === 'unavailable'" class="notice notice--warning" role="status">
        段落身份不存在于指定产物；保留当前 Run 和产物。
      </p>
      <template v-if="selectedPresentation">
        <section class="evidence-section" aria-label="F6 交付物">
          <h2>F6 交付物 · {{ selectedPresentation.mode }}</h2>
          <p>产物身份：{{ selectedPresentation.artifact?.id ?? 'unavailable' }}</p>
          <p>独立输出身份：{{ selectedPresentation.output_request?.id ?? 'unavailable' }}</p>
          <p>来源版本：状态 {{ selectedPresentation.source_versions?.state_revision ?? 'unknown' }} · 图 {{ selectedPresentation.source_versions?.graph_version ?? 'unknown' }} · 规格 {{ selectedPresentation.source_versions?.specification_version ?? 'unknown' }}</p>
          <p v-if="selectedPresentation.freshness === 'needs_review'" class="notice notice--warning" role="status">
            来源版本已变化；以下等级是历史快照，不能作为当前有效等级。
          </p>
          <div class="f7-grades" aria-label="保存的验证等级">
            <span v-for="grade in selectedPresentation.grade_labels" :key="grade" class="f7-grade">{{ grade }}</span>
            <span v-if="!selectedPresentation.grade_labels.length">没有当前可展示的已确认等级</span>
          </div>
          <p>交付：{{ selectedPresentation.delivery?.grade ?? 'not_verified' }} · {{ selectedPresentation.status ?? 'unknown' }}</p>
          <pre class="f7-answer">{{ selectedPresentation.answer ?? '答案不可用' }}</pre>
          <h3>输出段落与锚点</h3>
          <ol class="f7-paragraphs">
            <li v-for="paragraph in selectedPresentation.paragraphs" :id="`f7-${paragraph.id.replace(':', '-')}`" :key="paragraph.id"
              :aria-current="paragraph.id === selected.paragraphId ? 'location' : undefined">
              <h4>{{ paragraph.id }} · {{ paragraph.status }} · {{ paragraph.grade }}</h4>
              <p>{{ paragraph.text }}</p>
              <small>来源：<a v-for="refId in paragraph.claim_refs" :key="refId" :href="`#f7-source-${encodeURIComponent(refId)}`">{{ refId }}</a>{{ paragraph.claim_refs.length ? '' : '无当前来源' }}</small>
              <a :href="paragraphHref(paragraph.id)">此段落的固定链接</a>
            </li>
          </ol>
          <h3>证据来源</h3>
          <ul class="f7-sources">
            <li v-for="source in selectedPresentation.sources" :id="`f7-source-${encodeURIComponent(source.id)}`" :key="source.id">
              <strong>{{ source.kind ?? 'VerificationRecord' }}</strong> · {{ source.grade ?? 'not_verified' }} · {{ source.scope ?? 'scope 未记录' }}
              <p>{{ source.id }} · {{ source.status ?? 'unknown' }}</p>
              <p v-if="source.specification_version !== undefined">规格版本 {{ source.specification_version }} · {{ source.target_hash ?? '' }}</p>
              <a v-if="source.node_id && source.graph_version !== undefined" :href="sourceHref(source.node_id, source.graph_version)">定位来源图节点 {{ source.node_id }}</a>
            </li>
          </ul>
        </section>
      </template>
      <section class="evidence-section" aria-label="证明依赖图">
        <h2>证明依赖图</h2>
        <p v-if="detail.graph_target.status === 'unavailable'" role="status">指定图版本或节点不存在；已保留当前 Run。</p>
        <p v-else-if="!detail.graph">此 Run 没有已持久化的公开依赖图。</p>
        <template v-else>
          <p v-if="detail.graph.data_origin === 'synthetic_f7_performance'" class="notice notice--warning" role="status">
            这是 synthetic 500 节点性能样本，不代表真实 Run 的数学依赖图。
          </p>
          <FaithfulDependencyGraph :graph="detail.graph" :selected-node-id="selected.nodeId" :href-for-node="nodeHref" />
        </template>
      </section>
    </template>
  </PageFrame>
</template>

<style scoped>
.f7-toolbar,.f7-run-list li,.f7-grades { display:flex; flex-wrap:wrap; align-items:center; gap:.75rem; }
.f7-toolbar { justify-content:space-between; margin-bottom:1rem; }
.f7-run-list,.f7-paragraphs,.f7-sources { display:grid; gap:.8rem; padding-left:1.25rem; }
.f7-run-list li,.f7-paragraphs li,.f7-sources li { border-bottom:1px solid var(--border); padding:.75rem 0; }
.f7-run-list time,.f7-run-list span:last-of-type,.f7-paragraphs small,.f7-nodes small { color:var(--muted); }
.f7-grade { border:1px solid var(--border); border-radius:999px; padding:.2rem .65rem; font-weight:650; }
.f7-answer { white-space:pre-wrap; overflow-wrap:anywhere; font:inherit; }
.f7-sources,.f7-run-list,.f7-paragraphs,.evidence-section { overflow-wrap:anywhere; }
.f7-paragraphs li[aria-current="location"] { outline:2px solid var(--accent); outline-offset:4px; }
.f7-paragraphs a { display:block; margin-top:.45rem; }
</style>
