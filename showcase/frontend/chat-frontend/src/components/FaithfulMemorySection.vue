<script setup lang="ts">
import type { PopulationMemoryResponse, RunMemoryResponse } from '../api/memory.schemas'

type MemoryResult<T> = { status: 'loading' | 'unavailable' | 'error' } | { status: 'available'; data: T }

const props = defineProps<{
  runMemory: MemoryResult<RunMemoryResponse>
  populationMemory: MemoryResult<PopulationMemoryResponse>
}>()

const runFields = [
  ['run_id', 'Run ID'],
  ['source', '来源'],
  ['state_revision', '状态修订'],
  ['phase', '阶段'],
  ['status', '状态'],
  ['plan_version', '计划版本'],
  ['graph_version', '图版本'],
  ['budget', '预算'],
  ['invalidated_count', '已失效记录数'],
] as const

function display(value: unknown): string {
  if (value === null || value === undefined) return '未知（未提供）'
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function evidenceItems(value: unknown): Record<string, unknown>[] {
  if (Array.isArray(value)) return value.filter(isRecord)
  if (!isRecord(value)) return []
  if ('evidence_level' in value || 'result_id' in value) return [value]
  return Object.values(value).filter(isRecord)
}

function hasEvidence(value: unknown): boolean {
  if (value === null || value === undefined || value === '') return false
  if (Array.isArray(value)) return value.length > 0
  if (typeof value === 'number') return value > 0
  if (isRecord(value)) return Object.keys(value).length > 0
  return true
}

function evidenceLabel(evidence: Record<string, unknown>, index: number): string {
  const id = evidence.result_id
  return id === undefined || id === null ? `证据 ${index + 1}` : `证据 ${index + 1} · ${display(id)}`
}

function evidenceKey(evidence: Record<string, unknown>, index: number): string {
  const id = evidence.result_id
  return id === undefined || id === null ? String(index) : String(id)
}
</script>

<template>
  <section v-if="props.runMemory.status !== 'unavailable' || props.populationMemory.status !== 'unavailable'" class="evidence-section" aria-label="运行记忆与历史路线观察">
    <template v-if="props.runMemory.status === 'available'">
      <h2>运行记忆</h2>
      <p>只读的本次运行状态与证据记录；展示等级不会扩大其验证范围。</p>
      <dl class="data-list">
        <template v-for="[field, label] in runFields" :key="field">
          <dt>{{ label }}</dt>
          <dd>{{ display(props.runMemory.data.run_memory[field]) }}</dd>
        </template>
      </dl>
      <h3>有效证据与等级</h3>
      <p v-if="!hasEvidence(props.runMemory.data.run_memory.valid_evidence)" class="muted" role="status">当前没有有效证据记录。</p>
      <p v-else-if="!evidenceItems(props.runMemory.data.run_memory.valid_evidence).length">有效证据记录：{{ display(props.runMemory.data.run_memory.valid_evidence) }} · 等级：未知（未提供）</p>
      <ul v-else aria-label="有效证据记录">
        <li v-for="(evidence, index) in evidenceItems(props.runMemory.data.run_memory.valid_evidence)" :key="evidenceKey(evidence, index)">
          {{ evidenceLabel(evidence, index) }} · 等级：{{ display(evidence.evidence_level) }} · 类别：{{ display(evidence.category) }}
        </li>
      </ul>
    </template>

    <p v-else-if="props.runMemory.status === 'loading'" role="status" aria-busy="true">正在读取本次运行记忆…</p>
    <p v-else-if="props.runMemory.status === 'error'" class="notice notice--warning" role="status">本次运行记忆暂时无法读取。</p>

    <section v-if="props.populationMemory.status === 'available'" aria-label="历史路线观察">
      <h2>历史路线观察</h2>
      <p>权限范围：{{ props.populationMemory.data.authority }}。这些记录仅供观察，不构成数学证明，也不表示 verified_gain。</p>
      <p>记录总数：{{ props.populationMemory.data.total_jobs }} · 本页：{{ props.populationMemory.data.observations.length }} · 每页：{{ props.populationMemory.data.limit }} · 偏移：{{ props.populationMemory.data.offset }}</p>
      <p v-if="!props.populationMemory.data.observations.length" class="muted" role="status">没有可显示的历史路线观察。</p>
      <article v-for="(observation, index) in props.populationMemory.data.observations" :key="`${observation.source_run_id}:${observation.route_id}:${index}`">
        <dl class="data-list">
          <dt>来源 Run</dt><dd>{{ observation.source_run_id }}</dd>
          <dt>来源状态修订</dt><dd>{{ observation.source_state_revision }}</dd>
          <dt>路线 / 父路线</dt><dd>{{ observation.route_id }} / {{ display(observation.parent_route_id) }}</dd>
          <dt>状态 / 停止原因</dt><dd>{{ observation.status }} / {{ display(observation.stop_reason) }}</dd>
          <dt>图 / 计划 / 策略版本</dt><dd>{{ observation.graph_version }} / {{ observation.plan_version }} / {{ observation.policy_version }}</dd>
          <dt>未知观察数</dt><dd>{{ display(observation.unknown_observation_count) }}</dd>
        </dl>
      </article>
    </section>
    <p v-else-if="props.populationMemory.status === 'loading'" role="status" aria-busy="true">正在读取历史路线观察…</p>
    <p v-else-if="props.populationMemory.status === 'error'" class="notice notice--warning" role="status">历史路线观察暂时无法读取。</p>
  </section>
</template>
