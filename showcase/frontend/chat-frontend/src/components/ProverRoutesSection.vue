<script setup lang="ts">
import type { ProverRoute } from '../api/reports.schemas'
import StatusBadge from './ui/StatusBadge.vue'

defineProps<{ routes: ProverRoute[] }>()

const backendLabels: Record<string, string> = {
  llm_prover: 'LLM 推导',
  math_tool_backend: '计算工具',
  lean_tactic_prover: 'Lean 后端',
}
const targetLabels: Record<string, string> = {
  natural_language_draft: '自然语言推导草稿',
  computable: '可计算目标',
  stable_lean_goal: '稳定 Lean Goal',
}
const selectionReasons: Record<string, string> = {
  'solver_role:explore': '求解器进入自然语言探索阶段',
  'solver_role:explore_polish': '求解器请求整理自然语言草稿',
  'solver_role:reasoner': '求解器进入步骤推理阶段',
  'solver_role:reason_noncoding': '求解器进入纯推理步骤',
  explicit_registered_tool_request: '步骤明确请求已注册的计算工具',
  explicit_formal_policy: 'Run 显式启用受限形式化验证',
  explicit_retry: '用户显式创建重试 attempt',
  explicit_switch: '用户显式切换后端',
}

function gradeLabel(value: string | null): string {
  return value ?? '未形成验证等级'
}
function selectionLabel(value?: string): string {
  return value ? selectionReasons[value] ?? value : '未记录'
}

/** Shows each expected route cost and keeps unknown separate from missing data. */
function costSummary(route: ProverRoute): string {
  const cost = route.cost
  const usage = typeof cost.usage === 'object' && cost.usage !== null
    ? cost.usage as Record<string, unknown>
    : {}
  const field = (source: Record<string, unknown>, key: string, label: string,
    format: (value: number) => string = String): string => {
    if (!(key in source)) return `${label} 未记录`
    if (source[key] === null || typeof source[key] !== 'number') return `${label} 未知`
    return `${label}：${format(source[key] as number)}`
  }
  let values: string[]
  if (route.backend_id === 'llm_prover') {
    values = [
      field(cost, 'prompt_tokens', '输入 token'),
      field(cost, 'completion_tokens', '输出 token'),
      field(cost, 'total_tokens', '总 token'),
    ]
  } else if (route.backend_id === 'math_tool_backend') {
    values = [
      field(cost, 'duration_seconds', '耗时', value => `${Number(value.toFixed(3))} 秒`),
      field(cost, 'observed_output_bytes', '输出', value => `${value} 字节`),
    ]
  } else if (route.backend_id === 'lean_tactic_prover') {
    values = [
      field(cost, 'elapsed_seconds', '耗时', value => `${Number(value.toFixed(3))} 秒`),
      field(cost, 'output_bytes', '输出', value => `${value} 字节`),
      field(usage, 'cpu_usage_usec', 'CPU', value => `${value} 微秒`),
      field(usage, 'memory_peak_bytes', '内存峰值', value => `${value} 字节`),
    ]
  } else {
    values = []
  }
  if (cost.unknown === true) values.push('用量结算未知')
  return values.length ? values.join(' · ') : '成本未记录'
}
</script>

<template>
  <section class="prover-routes" aria-label="证明后端路线">
    <h3>后端尝试与验证等级</h3>
    <p>草稿、有限计算和形式目标各自保留来源与等级上限。</p>
    <ol>
      <li v-for="route in routes" :key="route.attempt_id">
        <div class="route-heading">
          <strong>{{ backendLabels[route.backend_id] ?? route.backend_id }}</strong>
          <StatusBadge :value="route.status" />
        </div>
        <dl>
          <dt>目标</dt><dd>{{ targetLabels[route.target_type] ?? route.target_type }}</dd>
          <dt>本次等级</dt><dd>{{ gradeLabel(route.grade) }}</dd>
          <dt>最高等级</dt><dd>{{ route.maximum_grade }}</dd>
          <dt>选择依据</dt><dd>{{ selectionLabel(route.selection_reason) }}</dd>
          <dt>Attempt</dt><dd>{{ route.attempt_id }}</dd>
          <dt v-if="route.parent_attempt_id">父 Attempt</dt>
          <dd v-if="route.parent_attempt_id">{{ route.parent_attempt_id }}</dd>
          <dt>成本</dt><dd>{{ costSummary(route) }}</dd>
        </dl>
        <details class="route-contract">
          <summary>后端契约元数据</summary>
          <dl>
            <dt>输入格式</dt><dd>{{ route.input_format ?? '未记录' }}</dd>
            <dt>输出格式</dt><dd>{{ route.output_format ?? '未记录' }}</dd>
            <dt>确定性</dt><dd>{{ route.deterministic === true ? '是' : route.deterministic === false ? '否' : '未知' }}</dd>
            <dt>环境身份</dt><dd>{{ JSON.stringify(route.environment_identity ?? {}) }}</dd>
            <dt v-if="route.unavailable_reason">不可用原因</dt>
            <dd v-if="route.unavailable_reason">{{ route.unavailable_reason }}</dd>
          </dl>
        </details>
      </li>
    </ol>
    <p>LLM_REVIEWED 表示语言模型审查，不等于 L1、L2 或 L3 形式证据。</p>
  </section>
</template>

<style scoped>
.prover-routes { margin-block: 1rem; }
.prover-routes ol { display: grid; gap: .75rem; padding-inline-start: 1.25rem; }
.prover-routes li { border: 1px solid var(--border, #d7dde5); border-radius: .5rem; padding: .75rem; }
.route-heading { display: flex; align-items: center; justify-content: space-between; gap: .5rem; }
.prover-routes dl { display: grid; grid-template-columns: minmax(7rem, auto) 1fr; gap: .3rem .75rem; overflow-wrap: anywhere; }
.prover-routes dt { color: var(--muted, #596579); }
.prover-routes dd { margin: 0; }
</style>
