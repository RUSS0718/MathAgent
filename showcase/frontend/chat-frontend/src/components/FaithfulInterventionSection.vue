<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { api } from '../api/client'
import { isApiError } from '../api/errors'
import type { InterventionsView } from '../api/interventions.schemas'
import { createIdempotencyKey } from '../runtime/jobs/idempotency'
import UiButton from './ui/UiButton.vue'
import FaithfulInterventionSetup from './FaithfulInterventionSetup.vue'

const props = defineProps<{ jobId: string; allowedActions: string[]; refreshToken: number }>()
type ViewState = { status: 'loading' | 'unavailable' | 'error' } | { status: 'available'; data: InterventionsView }
const view = ref<ViewState>({ status: 'loading' })
const pending = ref('')
const notice = ref('')
const error = ref('')
let generation = 0
let pairPoll: ReturnType<typeof setTimeout> | undefined
let pollingPair = ''
let pollingPause = false

async function load(): Promise<void> {
  const current = ++generation
  view.value = { status: 'loading' }
  error.value = ''
  try {
    const data = await api.interventions(props.jobId)
    if (current === generation) {
      view.value = { status: 'available', data: data.interventions }
      const pair = data.interventions.pairs.find(item => item.pair_id === pollingPair)
      clearTimeout(pairPoll)
      if (pair && ['reserved', 'running'].includes(String(pair.status))) {
        pairPoll = setTimeout(() => { void load() }, 1200)
      } else if (pollingPause && data.interventions.status === 'pause_requested') {
        pairPoll = setTimeout(() => { void load() }, 1200)
      } else {
        pollingPair = ''
        pollingPause = false
      }
    }
  } catch (cause) {
    if (current !== generation) return
    if (isApiError(cause) && cause.status === 404) view.value = { status: 'unavailable' }
    else { view.value = { status: 'error' }; error.value = cause instanceof Error ? cause.message : '同源干预记录暂时无法读取。' }
  }
}

async function mutate(name: string, operation: () => Promise<unknown>, message: string): Promise<void> {
  pending.value = name
  error.value = ''
  notice.value = ''
  try {
    await operation()
    notice.value = message
    await load()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '操作未能确认，请刷新持久状态。'
    await load()
  } finally { pending.value = '' }
}

async function pause(): Promise<void> {
  pollingPause = true
  await mutate('pause', () => api.requestInterventionPause(props.jobId), '已请求暂停；运行会在安全步骤边界进入等待输入。')
}

async function execute(pairId: string): Promise<void> {
  pollingPair = pairId
  await mutate(`execute:${pairId}`, () => api.executeInterventionPair(props.jobId, pairId), '配对执行已排队；未完成的分支不会被当作成功。')
}

async function resume(): Promise<void> {
  if (!props.allowedActions.includes('resume_intervention') || pending.value) return
  await mutate('resume', () => api.resumeInterventionParent(props.jobId, createIdempotencyKey()), '已请求在原 Run 中显式续算。')
}

watch(() => [props.jobId, props.refreshToken], () => { void load() }, { immediate: true })
onUnmounted(() => { generation += 1; clearTimeout(pairPoll) })
</script>

<template>
  <section v-if="view.status !== 'unavailable'" class="evidence-section intervention-section" aria-label="同源干预实验" :aria-busy="pending ? 'true' : undefined">
    <h2>同源干预</h2>
    <p>在合法串行步骤 checkpoint 上比较一个登记方法变化。每个分支先由 Verifier 审查，随后用新调用身份对同一报告再审查一次；主任务通过显式成果引用核对适用性后继续，保留来源和原证据等级。</p>
    <p v-if="view.status === 'loading'" role="status" aria-busy="true">正在读取干预状态…</p>
    <div v-else-if="view.status === 'error'" class="notice notice--warning" role="alert">{{ error }} <UiButton @click="load">重试读取</UiButton></div>
    <template v-else-if="view.status === 'available'">
      <dl class="data-list"><dt>控制状态</dt><dd>{{ view.data.status }}</dd><dt>安全 checkpoint 修订</dt><dd>{{ view.data.checkpoint_revision ?? '无' }}</dd></dl>
      <div v-if="error" class="notice notice--error" role="alert">{{ error }}</div>
      <p v-if="notice" role="status" aria-live="polite">{{ notice }}</p>
      <div class="action-row">
        <UiButton v-if="allowedActions.includes('pause')" :busy="pending === 'pause'" :disabled="Boolean(pending)" @click="pause">请求安全暂停</UiButton>
        <UiButton :disabled="Boolean(pending)" @click="load">刷新干预状态</UiButton>
        <UiButton v-if="allowedActions.includes('resume_intervention')" variant="primary" :busy="pending === 'resume'" :disabled="Boolean(pending)" @click="resume">显式恢复父 Run</UiButton>
      </div>
      <FaithfulInterventionSetup v-if="view.data.status === 'paused'" :job-id="jobId" :view="view.data" @changed="load" />
      <h3>配对报告</h3>
      <p v-if="!view.data.pairs.length" class="muted" role="status">当前没有已预留的同源配对。</p>
      <article v-for="pair in view.data.pairs" :key="String(pair.pair_id)" class="intervention-pair">
        <div class="intervention-pair__heading"><strong>配对 {{ pair.pair_id }}</strong><span>{{ pair.status }}</span></div>
        <dl class="data-list">
          <dt>已启动分母</dt><dd>{{ pair.denominator ?? 0 }}</dd>
          <dt>可评估配对</dt><dd>{{ pair.evaluable_pairs ?? 0 }}</dd>
          <dt>差异</dt><dd>{{ pair.effect ?? '未知（未提供）' }}</dd>
          <dt>预算预留</dt><dd>{{ pair.budget_reservation ?? '未知（未提供）' }}</dd>
        </dl>
        <div class="intervention-arms">
          <section v-for="armName in ['control', 'intervention']" :key="armName">
            <h4>{{ armName === 'control' ? '控制臂' : '干预臂' }}</h4>
            <p>状态：{{ (pair.arms as Record<string, Record<string, unknown>> | undefined)?.[armName]?.status ?? '未知' }}</p>
            <p>成本：{{ (pair.arms as Record<string, Record<string, unknown>> | undefined)?.[armName]?.cost ?? '未知（未提供）' }}</p>
            <p>分支执行时 Verifier 裁决：{{ (pair.arms as Record<string, Record<string, unknown>> | undefined)?.[armName]?.branch_verifier_verdict ?? '未知（未提供）' }}</p>
            <p>新调用身份复核裁决：{{ (pair.arms as Record<string, Record<string, unknown>> | undefined)?.[armName]?.independent_recheck_verdict ?? '未知（未提供）' }}</p>
            <p>持久子状态一致性检查：{{ (pair.arms as Record<string, Record<string, unknown>> | undefined)?.[armName]?.evidence_integrity ?? '未知（未提供）' }}</p>
          </section>
        </div>
        <UiButton v-if="pair.status === 'reserved'" :busy="pending === `execute:${String(pair.pair_id)}`" :disabled="Boolean(pending)" @click="execute(String(pair.pair_id))">显式启动这组分支</UiButton>
      </article>
      <p class="muted">未知、未完成或未审查的分支保留在已启动分母中，不会被插补；单对结果只作描述性差异。</p>
    </template>
  </section>
</template>

<style scoped>
.intervention-pair { padding-block: var(--space-4); border-top: 1px solid var(--border); }
.intervention-pair__heading { display: flex; justify-content: space-between; flex-wrap: wrap; gap: var(--space-3); }
.intervention-arms { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-4); margin-block: var(--space-4); }
.intervention-arms section { min-width: 0; padding: var(--space-3); border: 1px solid var(--border); }
.intervention-arms h4 { margin: 0 0 var(--space-2); }
.intervention-arms p { margin: var(--space-1) 0; overflow-wrap: anywhere; }
@media (max-width: 760px) { .intervention-arms { grid-template-columns: 1fr; } }
</style>
