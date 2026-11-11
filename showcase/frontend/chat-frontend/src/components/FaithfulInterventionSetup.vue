<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '../api/client'
import type { InterventionFailureCategory, InterventionMethod, InterventionsView } from '../api/interventions.schemas'
import { createIdempotencyKey } from '../runtime/jobs/idempotency'
import UiButton from './ui/UiButton.vue'

const props = defineProps<{ jobId: string; view: InterventionsView }>()
const emit = defineEmits<{ changed: [] }>()
function createDraftIds() {
  const suffix = createIdempotencyKey().slice(0, 12)
  return { hypothesis: `hypothesis-${suffix}`, control: `control-${suffix}`,
    intervention: `intervention-${suffix}`, pair: `pair-${suffix}` }
}
const draftIds = ref(createDraftIds())
const hypothesisId = ref(draftIds.value.hypothesis)
const controlActionId = ref(draftIds.value.control)
const interventionActionId = ref(draftIds.value.intervention)
const pairId = ref(draftIds.value.pair)
const failureCategory = ref<InterventionFailureCategory>('method_mismatch')
const failureSymptom = ref('当前步骤未通过 Verifier 审查。')
const falsification = ref('独立 Verifier 接受相同义务下的干预步骤。')
const interventionMethod = ref<InterventionMethod>('induction')
const sourceEventId = ref('')
const selectedRoots = ref<string[]>([])
const seed = ref(17)
const pending = ref(false)
const error = ref('')
const success = ref('')
const methods: InterventionMethod[] = ['direct', 'contradiction', 'induction', 'construction', 'computation']
const availableSources = computed(() => props.view.failure_sources)
function isInterventionMethod(value: string | null): value is InterventionMethod {
  return value !== null && methods.includes(value as InterventionMethod)
}
const controlMethodAvailable = computed(() => isInterventionMethod(props.view.current_method_id))

watch(() => props.view.current_method_id, (method) => {
  if (isInterventionMethod(method) && method === interventionMethod.value) {
    interventionMethod.value = methods.find(item => item !== method) ?? 'direct'
  }
}, { immediate: true })

watch(() => props.view, (view) => {
  if (!sourceEventId.value && view.failure_sources.length) {
    sourceEventId.value = view.failure_sources[0]?.source_event_id ?? ''
  }
  if (selectedRoots.value.length === 0 && view.root_obligations.length === 1) {
    selectedRoots.value = [view.root_obligations[0]?.obligation_id ?? '']
  }
}, { immediate: true })

async function preparePair(): Promise<void> {
  const controlMethod = props.view.current_method_id
  if (!sourceEventId.value || selectedRoots.value.length === 0 || !isInterventionMethod(controlMethod)) return
  const source = availableSources.value.find(item => item.source_event_id === sourceEventId.value)
  if (!source) return
  pending.value = true
  error.value = ''
  success.value = ''
  try {
    const controlId = controlActionId.value.trim()
    const treatmentId = interventionActionId.value.trim()
    await api.createInterventionAction(props.jobId, {
      action_id: controlId, action_type: 'reasoning_method', target: 'current_step',
      parameters: { method_id: controlMethod },
    })
    await api.createInterventionAction(props.jobId, {
      action_id: treatmentId, action_type: 'reasoning_method', target: 'current_step',
      parameters: { method_id: interventionMethod.value },
    })
    await api.createInterventionHypothesis(props.jobId, {
      hypothesis_id: hypothesisId.value.trim(),
      failure_category: failureCategory.value,
      source_event_id: source.source_event_id,
      source_state_revision: source.source_state_revision,
      affected_roots: props.view.root_obligations.filter(item => selectedRoots.value.includes(item.obligation_id)),
      failure_symptom: failureSymptom.value.trim(),
      diagnostic_evidence: { event_type: source.event_type, verdict: source.verdict },
      candidate_action_ids: [controlId, treatmentId] as [string, string],
      falsification_criteria: { condition: falsification.value.trim() },
      priority: 50,
    })
    await api.reserveInterventionPair(props.jobId, {
      pair_id: pairId.value.trim(), hypothesis_id: hypothesisId.value.trim(),
      control_action_id: controlId, intervention_action_id: treatmentId, seed: seed.value,
    })
    success.value = '同源双臂已预留。请检查预算，再显式启动执行。'
    emit('changed')
    draftIds.value = createDraftIds()
    hypothesisId.value = draftIds.value.hypothesis
    controlActionId.value = draftIds.value.control
    interventionActionId.value = draftIds.value.intervention
    pairId.value = draftIds.value.pair
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '建立配对失败。已完成的注册项可在下方查看。'
    emit('changed')
  } finally { pending.value = false }
}
</script>

<template>
  <form class="intervention-form" @submit.prevent="preparePair">
    <h3>登记并预留单动作配对</h3>
    <p>两个分支继承当前暂停 checkpoint；父 Run 只保存独立账目与审阅结果，不自动合并分支证据。</p>
    <label>失败来源
      <select v-model="sourceEventId" required>
        <option v-for="source in availableSources" :key="source.source_event_id" :value="source.source_event_id">
          {{ source.step_label }} · {{ source.verdict }} · 修订 {{ source.source_state_revision }}
        </option>
      </select>
    </label>
    <fieldset class="intervention-roots" :disabled="pending">
      <legend>受影响根义务（至少选一项）</legend>
      <label v-for="root in view.root_obligations" :key="root.obligation_id" class="intervention-root">
        <input v-model="selectedRoots" type="checkbox" :value="root.obligation_id">
        <span>{{ root.proposition }}</span>
      </label>
    </fieldset>
    <div class="intervention-fields">
      <label>失败假设 ID<input v-model="hypothesisId" required maxlength="80"></label>
      <label>失败分类
        <select v-model="failureCategory">
          <option value="method_mismatch">方法不匹配</option>
          <option value="lemma_structure">引理结构</option>
          <option value="decomposition_granularity">分解粒度</option>
          <option value="inefficient_order">顺序低效</option>
          <option value="underused_premise">前提利用不足</option>
        </select>
      </label>
      <label>失败症状<input v-model="failureSymptom" required maxlength="240"></label>
      <label>反证条件<input v-model="falsification" required maxlength="240"></label>
      <label>控制动作 ID<input v-model="controlActionId" required maxlength="80"></label>
      <label>当前控制方法<input :value="view.current_method_id ?? 'unknown'" disabled></label>
      <label>干预动作 ID<input v-model="interventionActionId" required maxlength="80"></label>
      <label>干预方法
        <select v-model="interventionMethod">
          <option v-for="method in methods.filter(item => item !== view.current_method_id)" :key="method" :value="method">{{ method }}</option>
        </select>
      </label>
      <label>配对 ID<input v-model="pairId" required maxlength="80"></label>
      <label>随机化种子<input v-model.number="seed" type="number" min="0" step="1" required></label>
    </div>
    <p v-if="!controlMethodAvailable" class="notice notice--warning">当前步骤没有可登记的控制方法，本 checkpoint 不满足干预合同。</p>
    <p v-if="error" class="notice notice--error" role="alert">{{ error }}</p>
    <p v-if="success" role="status">{{ success }}</p>
    <UiButton type="submit" variant="primary" :busy="pending" :disabled="pending || !controlMethodAvailable || !availableSources.length || !view.root_obligations.length">登记并预留</UiButton>
  </form>
</template>

<style scoped>
.intervention-form { display: grid; gap: var(--space-3); padding-block: var(--space-4); }
.intervention-form h3, .intervention-form p { margin: 0; }
.intervention-form label { display: grid; gap: var(--space-1); color: var(--muted); font-size: var(--text-sm); }
.intervention-form input, .intervention-form select { min-width: 0; min-height: var(--control-height); padding: var(--space-2) var(--space-3); border: 1px solid var(--border-strong); border-radius: var(--radius-md); background: var(--surface); color: var(--text); }
.intervention-form select[multiple] { min-height: 7rem; }
.intervention-roots { display: grid; gap: var(--space-2); min-width: 0; margin: 0; padding: var(--space-3); border: 1px solid var(--border); }
.intervention-roots legend { padding-inline: var(--space-2); color: var(--muted); font-size: var(--text-sm); }
.intervention-root { display: flex !important; align-items: flex-start; gap: var(--space-2) !important; }
.intervention-root input { min-height: auto; margin-top: .2rem; }
.intervention-root span { overflow-wrap: anywhere; }
.intervention-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-3); }
@media (max-width: 760px) { .intervention-fields { grid-template-columns: 1fr; } }
</style>
