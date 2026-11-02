<script setup lang="ts">
import { computed, ref } from 'vue'
import type { JobReport } from '../api/reports.schemas'
import { api } from '../api/client'
import UiButton from './ui/UiButton.vue'
import StatusBadge from './ui/StatusBadge.vue'
const props = defineProps<{ report: JobReport; jobId: string }>()
const solver = computed(() => props.report.solver?.solver)
const steps = computed(() => (solver.value?.progress?.steps ?? []) as Record<string, unknown>[])
const failures = computed(() => (solver.value?.progress?.failures ?? []) as Record<string, unknown>[])
const replay = ref<Awaited<ReturnType<typeof api.candidateReplay>> | null>(null)
const notice = ref('')
const busy = ref(false)
const history = computed(() => Array.isArray(props.report.report.checks.history) ? props.report.report.checks.history as Record<string, unknown>[] : [])
function display(value: unknown): string { return value == null ? 'unknown（未知）' : typeof value === 'object' ? JSON.stringify(value) : String(value) }
async function loadReplay(): Promise<void> {
  busy.value = true
  try { replay.value = await api.candidateReplay(props.jobId); notice.value = '' }
  catch (error) { notice.value = error instanceof Error ? error.message : '候选重放不可用' }
  finally { busy.value = false }
}
</script>
<template>
  <template v-if="report.solver?.solver_mode?.startsWith('star_')">
    <section class="evidence-section" aria-label="STAR 持久进展">
      <h2>STAR 持久进展</h2>
      <div class="review-meta"><StatusBadge :value="report.solver.solver_mode" /><StatusBadge :value="report.solver.evidence_kind ?? 'unknown'" /></div>
      <p>以下状态来自同一 Run 的持久记录；工程注入与回放不代表真实模型效果。</p>
      <dl class="data-list"><template v-for="field in ['run_id', 'state_revision', 'phase', 'status']" :key="field"><dt>{{ field }}</dt><dd>{{ display(solver?.[field]) }}</dd></template></dl>
      <p v-if="report.solver.missing_capabilities?.length">模式限制：{{ report.solver.missing_capabilities.join('、') }}</p>
      <details open><summary>当前计划、步骤与回退记录</summary>
        <p>计划版本 {{ display(solver?.progress?.plan_version) }} · 尝试 {{ display(solver?.progress?.attempt_index) }} · Meta 裁定 {{ display(solver?.progress?.meta_decision) }}</p>
        <ol v-if="steps.length"><li v-for="(step, index) in steps" :key="index">{{ step.label }}{{ step.current ? '（当前）' : '' }} · 目标 {{ display(step.goal_gate) }} · 逻辑 {{ display(step.logic_gate) }} · {{ display(step.verdict) }} · {{ step.valid === true && step.verdict === 'ACCEPT' ? '已接受' : '尚未接受' }}</li></ol>
        <p v-else>尚无已保存计划摘要。</p>
        <p v-if="!failures.length">未触发回退或重规划。</p>
        <ul v-else><li v-for="(failure, index) in failures" :key="index">{{ failure.kind }} · 原计划 {{ failure.plan_version }} · 尝试 {{ failure.attempt_index }} · 失效 {{ failure.invalidated_count }} 项 · 救援 {{ failure.rescued_count }} 项</li></ul>
      </details>
      <details><summary>累计预算与未知消耗</summary><dl class="data-list"><template v-for="(value, field) in report.report.budget" :key="field"><dt>{{ field }}</dt><dd>{{ display(value) }}</dd></template></dl><p v-if="!report.report.budget">预算记录不可用；不按零消耗解释。</p></details>
    </section>
    <section class="evidence-section" aria-label="候选版本与选择">
      <h2>候选版本与选择</h2>
      <p>候选接受、有限计算与完整数学证明不同；失效版本保留供审阅。</p>
      <p v-if="!solver?.candidate_history?.length">尚无完整候选记录；不能据此判断求解成功。</p>
      <details v-for="(candidate, index) in solver?.candidate_history" :key="index"><summary>候选 {{ index + 1 }} · 版本 {{ candidate.version }} · {{ candidate.review_state }}</summary><dl class="data-list"><template v-for="field in ['candidate_id', 'answer_text', 'answer_hash', 'source_phase', 'plan_version', 'attempt_index', 'review_state', 'selection_eligible', 'invalidated_by', 'evidence_grade', 'dependency_refs']" :key="field"><dt>{{ field }}</dt><dd>{{ display(candidate[field]) }}</dd></template></dl></details>
      <details v-if="solver?.best_effort" open><summary>Best-Effort 确定性选择</summary><dl class="data-list"><template v-for="(value, field) in solver.best_effort" :key="field"><dt>{{ field }}</dt><dd>{{ display(value) }}</dd></template></dl></details>
      <UiButton :busy="busy" @click="loadReplay">零调用重放候选选择</UiButton>
      <p v-if="notice" role="status">{{ notice }}</p>
      <div v-if="replay"><StatusBadge value="replay" /><p>只重放已保存状态，不启动模型或工具。</p><details><summary>查看重放身份、审计与决定</summary><dl class="data-list"><dt>run_id</dt><dd>{{ replay.run_id }}</dd><dt>state_revision</dt><dd>{{ replay.state_revision }}</dd><dt>audit</dt><dd>{{ display(replay.audit) }}</dd><dt>decision</dt><dd>{{ display(replay.decision) }}</dd></dl></details></div>
    </section>
    <section class="evidence-section" aria-label="整题审查历史">
      <h2>整题审查历史</h2>
      <p>送审与交付身份必须一致；改写后旧裁决不自动继承。unknown 表示尚不能确认数学正确性。</p>
      <p v-if="!history.length">没有已保存的整题审查观察。</p>
      <details v-for="(check, index) in history" :key="index"><summary>观察 {{ index + 1 }} · {{ check.scope }} · {{ check.status }}</summary><dl class="data-list"><template v-for="field in ['artifact', 'checker_version', 'check_id', 'scope', 'limitations', 'source', 'versions', 'fact_sources', 'selection', 'evidence']" :key="field"><dt>{{ field }}</dt><dd>{{ display(check[field]) }}</dd></template></dl></details>
    </section>
  </template>
</template>
