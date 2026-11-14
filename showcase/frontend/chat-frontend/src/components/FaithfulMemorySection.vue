<script setup lang="ts">
import { ref, watch } from 'vue'
import { isApiError } from '../api/errors'
import { api } from '../api/client'
import type { PopulationMemoryControlResponse, PopulationMemoryResponse, RunMemoryResponse } from '../api/memory.schemas'

type MemoryResult<T> = { status: 'loading' | 'unavailable' | 'error' } | { status: 'available'; data: T }
type SessionPopulationMemory = PopulationMemoryControlResponse & { sessionId?: string }

const props = defineProps<{
  runMemory: MemoryResult<RunMemoryResponse>
  populationMemory: MemoryResult<PopulationMemoryResponse>
  populationMemoryControl: MemoryResult<SessionPopulationMemory>
}>()

const injectionEnabled = ref(false)
const injectionPending = ref(false)
const injectionUnavailable = ref(false)
const injectionError = ref('')
const observations = ref<PopulationMemoryControlResponse['observations']>([])
const sourceSessionId = ref('')
const loadedSourceId = ref('')
const sourceObservations = ref<PopulationMemoryControlResponse['observations']>([])
const selectedRecordId = ref('')
const managementMessage = ref('')

watch(sourceSessionId, () => {
  loadedSourceId.value = ''
  sourceObservations.value = []
  selectedRecordId.value = ''
})

watch(() => props.populationMemoryControl, (memory) => {
  injectionUnavailable.value = false
  injectionError.value = ''
  sourceSessionId.value = ''
  managementMessage.value = ''
  if (memory.status === 'available') {
    injectionEnabled.value = memory.data.injection_enabled
    observations.value = memory.data.observations
  }
}, { immediate: true })

async function manageMemory(action: 'load' | 'import' | 'clear'): Promise<void> {
  const control = props.populationMemoryControl
  if (control.status !== 'available' || !control.data.sessionId || injectionPending.value) return
  const sessionId = control.data.sessionId
  const sourceId = sourceSessionId.value.trim()
  if (action === 'load' && !sourceId) return
  if (action === 'import' && (!selectedRecordId.value || loadedSourceId.value !== sourceId)) return
  injectionPending.value = true
  injectionError.value = ''
  managementMessage.value = ''
  try {
    if (action === 'load') {
      sourceObservations.value = []
      selectedRecordId.value = ''
      loadedSourceId.value = ''
      const result = await api.populationMemoryControl(sourceId)
      sourceObservations.value = result.observations
      loadedSourceId.value = sourceId
      managementMessage.value = result.observations.length ? '来源已读取；请选择观察并显式导入。' : '来源会话没有可导入的观察。'
    } else {
      if (action === 'import') {
        await api.importPopulationMemory(sessionId, loadedSourceId.value, selectedRecordId.value)
        managementMessage.value = '已导入所选观察；仅作经验参考。'
      } else {
        await api.clearPopulationMemory(sessionId)
        observations.value = []
        managementMessage.value = '已清理此会话记忆；保留历史审计与有效数学账本。'
      }
      const result = await api.populationMemoryControl(sessionId)
      observations.value = result.observations
      injectionEnabled.value = result.injection_enabled
    }
  } catch (error) {
    injectionError.value = error instanceof Error ? `记忆管理失败：${error.message}` : '记忆管理失败；服务端状态无法确认。'
  } finally {
    injectionPending.value = false
  }
}

async function updateInjection(enabled: boolean): Promise<void> {
  if (props.populationMemoryControl.status !== 'available' || !props.populationMemoryControl.data.sessionId || injectionPending.value) return
  injectionPending.value = true
  injectionError.value = ''
  try {
    const result = await api.setPopulationMemoryInjection(props.populationMemoryControl.data.sessionId, enabled)
    injectionEnabled.value = result.injection_enabled
  } catch (error) {
    if (isApiError(error) && error.status === 404) injectionUnavailable.value = true
    injectionError.value = error instanceof Error ? `保存注入设置失败：${error.message}` : '保存注入设置失败；服务端状态无法确认。'
  } finally {
    injectionPending.value = false
  }
}

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
  if (['evidence_level', 'grade', 'id', 'evidence_id', 'result_id'].some(key => key in value)) return [value]
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
  const id = evidence.result_id ?? evidence.id ?? evidence.evidence_id
  return id === undefined || id === null ? `证据 ${index + 1}` : `证据 ${index + 1} · ${display(id)}`
}

function evidenceKey(evidence: Record<string, unknown>, index: number): string {
  const id = evidence.result_id ?? evidence.id ?? evidence.evidence_id
  return id === undefined || id === null ? String(index) : String(id)
}
</script>

<template>
  <section v-if="props.runMemory.status !== 'unavailable' || props.populationMemory.status !== 'unavailable' || props.populationMemoryControl.status !== 'unavailable'" class="evidence-section" aria-label="运行记忆与历史路线观察">
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
          {{ evidenceLabel(evidence, index) }} · 等级：{{ display(evidence.evidence_level ?? evidence.grade) }} · 类别：{{ display(evidence.category) }}
        </li>
      </ul>
      <section aria-label="经验记忆使用与决策">
        <h3>经验记忆使用与决策</h3>
        <p>检索或注入不表示采用；经验仅供参考，不构成数学证明。</p>
        <p v-if="!props.runMemory.data.run_memory.memory_usage.length" class="muted" role="status">没有可显示的记忆使用报告；不能据此推断采用或拒绝。</p>
        <article v-for="usage in props.runMemory.data.run_memory.memory_usage" :key="usage.call_id">
          <dl class="data-list">
            <dt>调用</dt><dd>{{ usage.call_id }}</dd>
            <dt>检索/注入记录</dt><dd>{{ usage.record_ids.length ? usage.record_ids.join('、') : '无记录' }}</dd>
          </dl>
          <p v-if="usage.decision_status === 'not_reported'">未报告采用或拒绝（not_reported）</p>
          <template v-else>
            <p>已报告决策（reported）</p>
            <p v-if="!usage.decisions.length" class="muted">没有明确的采用或拒绝条目。</p>
            <ul v-else aria-label="明确记忆决策">
              <li v-for="(decision, index) in usage.decisions" :key="`${decision.record_id}:${index}`">{{ decision.record_id }} · {{ decision.decision === 'adopt' ? '明确采用（adopt）' : '明确拒绝（reject）' }} · 原因：{{ decision.reason || '未提供' }}</li>
            </ul>
          </template>
        </article>
      </section>
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
    <p v-else-if="props.populationMemory.status === 'unavailable'" class="muted" role="status">此会话的历史路线观察不可用。</p>
    <section v-if="props.populationMemoryControl.status === 'available'" aria-label="会话记忆观察与注入设置">
      <h2>会话记忆观察</h2>
      <p>历史记忆仅供参考，不代表已验证的数学结论或收益。</p>
      <div v-if="props.populationMemoryControl.data.sessionId && !injectionUnavailable">
        <label>
          <input
            type="checkbox"
            :checked="injectionEnabled"
            :disabled="injectionPending"
            aria-describedby="population-memory-injection-help"
            @change="updateInjection(($event.target as HTMLInputElement).checked)"
          >
          启用此会话的 Population Memory 注入
        </label>
        <p id="population-memory-injection-help" class="muted">服务端启用 Population Memory 功能时，此开关允许本会话读取并注入历史观察，也允许记录终态 Run 的观察。关闭后不再记录或注入；关闭、清理或来源撤销后，后续模型请求（包括继续及重启恢复）都会重新核验当前授权和来源，不再使用失效经验。已发出的请求无法撤回；历史审计与有效数学账本保留。</p>
        <form @submit.prevent="manageMemory('load')">
          <label for="memory-source-session">来源会话 ID</label>
          <input id="memory-source-session" v-model="sourceSessionId" :disabled="injectionPending" required>
          <button type="submit" :disabled="injectionPending || !sourceSessionId.trim()">读取来源观察</button>
        </form>
        <p class="muted">仅允许同所有者会话显式导入；读取来源不会自动导入或启用注入，服务端会复核所有祖先来源。</p>
        <label for="memory-source-observation">来源观察</label>
        <select id="memory-source-observation" v-model="selectedRecordId" :disabled="injectionPending || !sourceObservations.length">
          <option value="">请选择来源观察</option>
          <option v-for="item in sourceObservations" :key="item.record_id" :value="item.record_id">{{ item.record_id }}</option>
        </select>
        <p v-for="item in sourceObservations" :key="item.record_id">来源 {{ item.record_id }}：{{ display(item.provenance) }}</p>
        <button type="button" :disabled="injectionPending || !selectedRecordId || loadedSourceId !== sourceSessionId.trim()" @click="manageMemory('import')">显式导入所选观察</button>
        <button type="button" :disabled="injectionPending" @click="manageMemory('clear')">清理此会话记忆</button>
        <p v-if="managementMessage" role="status" aria-live="polite">{{ managementMessage }}</p>
        <p v-if="injectionPending" role="status" aria-busy="true">正在处理记忆管理请求…</p>
        <p v-else role="status" aria-live="polite">服务端报告的注入状态：{{ injectionEnabled ? '启用' : '停用' }}</p>
        <p v-if="injectionError" class="notice notice--warning" role="alert">{{ injectionError }}</p>
      </div>
      <p v-else class="notice notice--warning" role="status">此会话的记忆注入控制不可用。</p>
      <p v-if="!observations.length" class="muted" role="status">没有可显示的记忆观察。</p>
      <article v-for="observation in observations" :key="observation.record_id">
        <dl class="data-list">
          <dt>结果观察</dt><dd>{{ display(observation.observation.outcome) }}</dd>
          <dt>适用范围</dt><dd>{{ display(observation.observation.applicability) }}</dd>
          <dt>版本</dt><dd>{{ display(observation.observation.versions) }}</dd>
          <dt>成本观察</dt><dd>{{ display(observation.observation.cost) }}</dd>
          <dt>来源记录</dt><dd>{{ display(observation.provenance) }}</dd>
        </dl>
      </article>
    </section>
    <p v-if="props.populationMemoryControl.status === 'loading'" role="status" aria-busy="true">正在读取会话记忆控制…</p>
    <p v-else-if="props.populationMemoryControl.status === 'error'" class="notice notice--warning" role="status">会话记忆控制暂时无法读取。</p>
    <p v-else-if="props.populationMemoryControl.status === 'unavailable'" class="muted" role="status">会话记忆注入控制不可用。</p>
  </section>
</template>

<style scoped>
input:not([type="checkbox"]), select { max-width: 100%; min-width: 0; }
</style>
