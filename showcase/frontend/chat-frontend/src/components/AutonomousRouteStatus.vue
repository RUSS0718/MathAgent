<script setup lang="ts">
/** Render only the committed selection and actual route progress. */
import { computed } from 'vue'
import { z } from 'zod'
import { populationProjectionSchema } from '../api/reports.schemas'

const props = defineProps<{ selection?: unknown; population?: unknown; executionSwitch?: unknown }>()
const selectionSchema = z.object({
  selected: z.enum(['serial', 'population']), reason: z.string(), proposal_reason: z.string(),
  independent_routes: z.number(),
  capacity: z.object({ max_inflight: z.number().nullable(), worker_slots: z.number().nullable() }),
  budget: z.object({
    logical_calls: z.number(), deadline_at: z.number(),
    limits: z.object({ max_model_calls: z.number(), max_tokens: z.number() }),
  }),
})
const selection = computed(() => {
  const parsed = selectionSchema.safeParse(props.selection)
  return parsed.success ? parsed.data : null
})
const population = computed(() => {
  const parsed = populationProjectionSchema.safeParse(props.population)
  return parsed.success ? parsed.data : null
})
const switchSchema = z.object({
  status: z.enum(['converging', 'needs_review', 'switched', 'canceled', 'rejected']),
  source: z.enum(['serial', 'population']), target: z.enum(['serial', 'population']),
  reason: z.string(), checkpoint_revision: z.number().int().nonnegative().nullable().optional(),
})
const executionSwitch = computed(() => {
  const parsed = switchSchema.safeParse(props.executionSwitch)
  return parsed.success ? parsed.data : null
})
const switchLabels = {
  converging: '切换中', needs_review: '待复核', switched: '已切换',
  canceled: '切换已取消', rejected: '切换未准入',
}
const modeLabel = (mode: string) => mode === 'population' ? '并发' : '串行'
const reasons: Record<string, string> = {
  independent_routes_admitted: '独立方向已通过容量与根预算准入',
  model_selected_serial: 'Agent 选择串行推进',
  no_population_proposal: '未提出并发路线，继续串行推进',
  population_not_enabled: '并发能力未配置，继续串行推进',
  independent_frontiers_required: '缺少可执行的独立方向，改用串行',
  parallel_capacity_unavailable: '并发容量不足，改用串行',
  root_budget_insufficient: '根预算不足以预留并发与整题收尾，改用串行',
  population_capacity_unverified: '并发容量尚未核实，改用串行',
}
</script>

<template>
  <section v-if="executionSwitch" aria-label="运行路线切换" aria-live="polite">
    <h3>{{ switchLabels[executionSwitch.status] }} · {{ modeLabel(executionSwitch.source) }} → {{ modeLabel(executionSwitch.target) }}</h3>
    <p>{{ executionSwitch.reason }}</p>
    <p v-if="executionSwitch.status === 'converging'">正在等待在途动作结算，受影响的新派发已停止。</p>
    <p v-if="executionSwitch.status === 'needs_review'">未知结果保留原预留，相关切换等待复核。</p>
    <p v-if="executionSwitch.status === 'switched' && executionSwitch.checkpoint_revision != null">检查点版本 {{ executionSwitch.checkpoint_revision }}；继续使用原任务预算与截止时间。</p>
  </section>
  <section v-if="selection" aria-label="自主路线选择">
    <h3>初始路线选择 · {{ selection.selected === 'population' ? 'Population/APRS 并发' : '串行/APRS' }}</h3>
    <p>{{ reasons[selection.reason] ?? selection.reason }}</p>
    <p v-if="selection.proposal_reason">{{ selection.proposal_reason }}</p>
    <p>独立方向 {{ selection.independent_routes }} · 并发上限 {{ selection.capacity.max_inflight ?? '未配置' }} · 执行槽 {{ selection.capacity.worker_slots ?? '未配置' }}</p>
    <p>选择时已用模型调用 {{ selection.budget.logical_calls }} / {{ selection.budget.limits.max_model_calls }}；根 token 上限 {{ selection.budget.limits.max_tokens }}。路线共享原预算和截止时间。</p>
  </section>
  <section v-if="population?.routes?.length" aria-label="实际求解路线">
    <h3>实际求解路线</h3>
    <ol>
      <li v-for="route in population.routes" :key="route.ordinal">
        路线 {{ route.ordinal }}<span v-if="route.parent_ordinal">（来源路线 {{ route.parent_ordinal }}）</span>
        · {{ route.status }} · 已接受步骤 {{ route.completed_steps }} / {{ route.step_count }}
        · {{ route.result === 'accepted_evidence' ? '已产生核验成果' : '尚无可采用成果' }}
      </li>
    </ol>
    <p v-if="population.scheduler.paused">派发受限，已保存成果与在途结算保留。</p>
    <p>路线成果仍需独立整题审查；迟到回执只结算归档。</p>
  </section>
</template>
