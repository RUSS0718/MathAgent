<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRoleStageReading } from '../runtime/jobs/role-stage-reading'
import { roleLabels, statusLabels } from '../runtime/jobs/causal-progress'
import { renderSafeMarkdown } from '../renderers/markdown-adapter'

const props = defineProps<{ jobId?: string; role: string; source?: string; savedSource?: string; jobStatus: string; runtimeState?: string; revision?: number }>()
const emit = defineEmits<{ filter: [role: string] }>()
const dialog = ref<HTMLDialogElement>()
const reading = useRoleStageReading()
const { context, content, loading, failed, pendingSource, expanded, scrollTop } = reading
const duties: Record<string, string> = {
  controller: '组织阶段安排与任务派发；协调安排不是数学推导。',
  explore: '探索题目结构、可行方法和候选结论。',
  planner: '安排求解目标、方法和步骤依赖。',
  reasoner: '执行计划步骤，提交推理结论和未解决点。',
  step_verifier: '检查指定步骤的结论及适用条件，不代替整题审查。',
  whole_solution_verifier: '审查指定整题候选的完整性与正确性。',
  final_generator: '整理候选答案；生成成功不代表审查通过。',
  meta: '评估处理策略并作出调整决议。',
  researcher: '查找与题目有关的资料、定义和方法。',
}
const runtimeLabels: Record<string, string> = { idle: '未参与', running: '执行中', completed: '已完成', failed: '遇到问题', unknown: '结果未知' }
const runtimeLabel = computed(() => props.runtimeState === 'idle' &&
  (loading.value || failed.value || content.value?.content_status !== 'empty' || content.value?.history.length)
  ? '参与状态未确认' : runtimeLabels[props.runtimeState ?? 'unknown'] ?? '状态待确认')
const validityLabels: Record<string, string> = { current: '当前版本有效', historical: '历史版本', replaced: '已替换', invalidated: '已失效' }
const checkStatusLabels: Record<string, string> = { accepted: '通过', rejected: '未通过', unknown: '结论未知', unreviewed: '未检查' }
const stageLabels: Record<string, string> = {
  planning: '阶段安排', exploration: '探索成果', step_submission: '步骤提交', research: '资料研究',
  counterexample_search: '反例查找', step_review: '步骤检查', classified_result: '分类成果',
  whole_review: '整题审查', final_candidate: '答案候选', meta_decision: '策略决议',
  meta_guidance: '策略建议', meta_execution: '策略执行', formal_target_review: '形式目标检查',
}
const historical = computed(() => Boolean(context.value?.historical || context.value?.source !== undefined))
const emptyText = computed(() => {
  if (historical.value && (!context.value?.source || content.value?.content_status === 'unavailable')) return '该条历史成果无法还原。'
  if (content.value?.content_status === 'not_published') return '成果内容未公开。'
  if (content.value?.content_status === 'unavailable' || !content.value) return '来源无法确认，成果暂不可用。'
  return props.runtimeState === 'idle' ? '未参与。' : '尚无已保存成果。'
})
const hiddenResults = computed(() => (content.value?.results ?? []).filter(result => !expanded.value.has(result.source_ref)))
let trigger: HTMLElement | undefined
let fallback: HTMLElement | undefined
let restoring = false
watch(() => props.jobId, () => { dialog.value?.close(); reading.close() })
watch(() => props.savedSource, source => { if (reading.isOpen.value && source) void reading.notify(source) })
watch(() => [props.revision, props.jobStatus, props.runtimeState], () => {
  if (reading.isOpen.value) void reading.notify()
})
watch(content, async () => {
  await nextTick()
  if (dialog.value) {
    dialog.value.scrollTop = scrollTop.value
    if (dialog.value.open && !dialog.value.contains(document.activeElement)) {
      dialog.value.querySelector<HTMLButtonElement>('[autofocus]')?.focus({ preventScroll: true })
    }
  }
})
async function open(invoker?: HTMLElement, stableControl?: HTMLElement) {
  restoring = true
  trigger = invoker ?? (document.activeElement instanceof HTMLElement ? document.activeElement : undefined)
  fallback = stableControl
  const request = reading.open({ jobId: props.jobId ?? '', role: props.role, source: props.source, historical: props.source !== undefined })
  const restoredTop = scrollTop.value
  await nextTick()
  if (!dialog.value?.open) dialog.value?.showModal()
  if (dialog.value) dialog.value.scrollTop = restoredTop
  await request
  await nextTick()
  if (dialog.value?.open) dialog.value.scrollTop = scrollTop.value
  restoring = false
  if (reading.isOpen.value && props.savedSource) void reading.notify(props.savedSource)
}
function recordScroll() {
  if (!restoring && dialog.value?.open) scrollTop.value = dialog.value.scrollTop
}
function closed() {
  if (dialog.value?.open) return
  reading.close()
  // Native dialog restores existing invokers. The region fallback covers removed/hidden entries.
  if (!trigger?.isConnected || !trigger.getClientRects().length) fallback?.focus()
}
function more() {
  if (hiddenResults.value.length) for (const result of hiddenResults.value) expanded.value.add(result.source_ref)
  else expanded.value = new Set(content.value?.results.slice(-3).map(result => result.source_ref))
}
defineExpose({ open })
</script>

<template>
  <dialog ref="dialog" aria-labelledby="role-stage-heading" @cancel="reading.close()" @close="closed" @scroll="recordScroll">
    <form method="dialog" @submit="reading.close()"><button autofocus>关闭</button></form>
    <h2 id="role-stage-heading">{{ roleLabels[role] }}阶段成果</h2>
    <p>任务：{{ statusLabels[jobStatus] ?? '状态待确认' }} · 角色：{{ runtimeLabel }}</p>
    <p>职责：{{ duties[role] }}</p>
    <p>{{ historical ? '历史成果' : '当前成果' }}</p>
    <p v-if="pendingSource" role="status">有新成果，<button type="button" @click="reading.update()">更新查看</button></p>
    <p v-if="loading" role="status">正在读取已保存成果…</p>
    <p v-if="historical && !context?.source">该条历史成果无法还原。</p>
    <p v-if="failed" role="alert">读取失败，最新状态未确认。</p>
    <p v-if="!loading && !failed && !content?.results.length && !(historical && !context?.source)">{{ emptyText }}</p>
    <section v-for="result in content?.results ?? []" :key="result.source_ref" data-plan-body>
      <h3>计划第 {{ result.plan_version }} 版 · {{ stageLabels[result.stage] ?? '阶段成果' }} · 第 {{ result.attempt_index + 1 }} 次尝试</h3>
      <p>{{ failed ? '最新状态未确认' : validityLabels[result.validity] ?? '有效性待确认' }}</p>
      <p>检查范围：{{ result.check.label || (result.check.scope === 'plan_structure' ? '计划结构校验通过，不代表目标已完成。' : '检查范围未记录，不代表整题通过。') }}</p>
      <p v-if="result.check.status">检查结论：{{ checkStatusLabels[result.check.status] ?? '结论未知' }}</p>
      <div v-if="expanded.has(result.source_ref)" data-stage-content>
        <template v-if="result.sections.length">
          <section v-for="(section, index) in result.sections" :key="index"><h4>{{ section.label }}</h4><div v-html="renderSafeMarkdown(section.text)" /></section>
        </template>
        <ol v-if="result.items.length"><li v-for="item in result.items" :key="item.label">
          <h4>{{ item.label }} · {{ item.title }}</h4><div v-html="renderSafeMarkdown(item.objective)" />
          <p>先后依赖：{{ item.depends_on.join('、') || '无前置步骤' }}</p>
        </li></ol>
        <p v-if="!result.sections.length && !result.items.length">方法、公式及未解决点未记录或未公开。</p>
      </div>
    </section>
    <button v-if="(content?.results.length ?? 0) > 3 || hiddenResults.length" type="button" :aria-expanded="!hiddenResults.length" @click="more">{{ hiddenResults.length ? `更多成果（${hiddenResults.length} 项）` : '收起更多成果' }}</button>
    <button v-if="failed" type="button" @click="reading.retry()">重试读取</button>
    <details v-if="content?.history.length"><summary>历史成果</summary><ul><li v-for="item in content.history" :key="item.source_ref">
      <button type="button" @click="reading.selectHistory(item.source_ref)">计划第 {{ item.plan_version }} 版 · {{ stageLabels[item.stage] ?? '阶段成果' }} · 第 {{ item.attempt_index + 1 }} 次尝试</button>
    </li></ul></details>
    <button v-if="historical" type="button" @click="reading.update()">查看当前成果</button>
    <button type="button" @click="emit('filter', role); reading.close(); dialog?.close()">只看该角色</button>
  </dialog>
</template>

<style scoped>
dialog { margin: 0 0 0 auto; width: min(560px, 80vw); height: 100dvh; max-height: 100dvh; padding: 24px; border: 1px solid var(--border); background: var(--surface); color: var(--text); overflow-y: auto; }
dialog:modal, dialog::backdrop { overscroll-behavior: contain; }
dialog::backdrop { overflow: hidden; background: #0005; }
dialog { overflow-anchor: none; }
form { float: right; }
p { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.65; }
button { padding: 8px 12px; background: var(--surface); color: var(--text); border: 1px solid var(--border-strong); cursor: pointer; }
button:focus-visible, summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
[data-stage-content] { overflow-wrap: anywhere; }
:deep(.katex-display) { overflow-x: auto; overflow-y: hidden; }
</style>
