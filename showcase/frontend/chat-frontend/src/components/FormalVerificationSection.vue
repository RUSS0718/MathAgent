<script setup lang="ts">
import { computed } from 'vue'
import type { FormalAttempt, FormalVerification } from '../api/reports.schemas'
import StatusBadge from './ui/StatusBadge.vue'

const props = defineProps<{ verification: FormalVerification }>()

const statusLabels: Record<string, string> = {
  disabled: '未启用',
  dispatched: '形式化验证进行中，尚未确认',
  unsupported: '当前目标不受支持',
  unavailable: '形式验证环境不可用',
  not_verified: '尚未验证',
  partial: '形式验证未完成',
  timeout: '形式验证超时',
  error: '形式验证出错',
  failed: '形式验证未通过',
  unknown: '形式验证结果未知',
  solved: '验证后端已返回结果，证据等级未确认',
}

const current = computed(() => props.verification.current)
const requirementUnmet = computed(() => props.verification.assessment?.status === 'unmet'
  || (props.verification.policy.require_formal === true && props.verification.assessment?.status !== 'met'))
const parentAttemptId = computed(() => props.verification.current?.parent_attempt_id ?? props.verification.lineage.parent_attempt_id ?? '无')
const backend = computed(() => stringValue(props.verification.policy.backend) || stringValue(props.verification.policy.requested_backend) || 'unknown')
const target = computed(() => objectValue(props.verification.policy.target))
const environment = computed(() => {
  const proofEnvironment = objectValue(current.value?.proof_artifact?.environment)
  return { ...objectValue(proofEnvironment.build_manifest), ...proofEnvironment,
    ...objectValue(props.verification.policy.environment) }
})
const totalCost = computed(() => objectValue(props.verification.lineage.total_cost))
const effectiveGrade = computed(() => {
  const record = props.verification
  return record.status === 'solved' && record.current?.status === 'solved' && record.current.grade === record.grade
    ? record.grade
    : null
})
const headline = computed(() => effectiveGrade.value === 'L3'
  ? reviewedCorrespondenceCount.value === correspondence.value.length
    ? '形式目标与规格对应已独立核验'
    : '形式验证等级已返回；对应审查字段不完整，待人工复核'
  : effectiveGrade.value === 'L2'
    ? '形式目标已核验；原题对应待独立复核'
    : props.verification.status === 'solved'
      ? '形式验证返回 solved，但没有可公开的 L2/L3 等级；原答案仍保留'
      : `${statusLabels[props.verification.status] ?? '形式验证状态未知'}；原答案仍保留`)
const attemptChain = computed(() => {
  const ids = Array.isArray(props.verification.lineage.attempt_ids)
    ? props.verification.lineage.attempt_ids.filter((value): value is string => typeof value === 'string')
    : []
  return ids.length ? ids : props.verification.attempts.map((attempt) => attempt.attempt_id)
})
const correspondence = computed(() => {
  const specifications = objectValue(props.verification.current?.specifications)
  return ['original_to_spec', 'spec_to_target', 'target_to_environment'].map((key) => ({
    key,
    label: key === 'original_to_spec' ? '原题 → 规格' : key === 'spec_to_target' ? '规格 → 形式目标' : '目标 → 环境',
    record: objectValue(specifications[key]),
  }))
})
const originalCorrespondence = computed(() => correspondence.value[0]!)
const reviewedCorrespondenceCount = computed(() => correspondence.value.filter((item) => stringValue(item.record.review_status) === 'reviewed').length)
const originalReviewLabel = computed(() => effectiveGrade.value === 'L3' || stringValue(originalCorrespondence.value.record.review_status) === 'reviewed'
  ? '已独立复核'
  : '待独立复核')

function objectValue(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}
function stringValue(value: unknown): string {
  return typeof value === 'string' ? value : ''
}
function numberValue(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value) ? String(value) : 'unknown（未知）'
}
function reviewStatus(value: unknown): string {
  if (value === 'reviewed') return '已复核'
  if (value === 'not_reviewed') return '待复核'
  return typeof value === 'string' && value ? value : '状态未知'
}
function attemptLabel(attempt: FormalAttempt): string {
  return `${attempt.attempt_id} · ${statusLabels[attempt.status] ?? '状态未知'}`
}
</script>

<template>
  <section class="formal-section" aria-label="形式验证">
    <div class="formal-heading">
      <div>
        <p class="formal-eyebrow">独立于原答案与 LLM_REVIEWED</p>
        <h2>形式验证</h2>
      </div>
      <div class="formal-badges">
        <StatusBadge :value="verification.status" />
        <StatusBadge v-if="effectiveGrade" :value="effectiveGrade" />
      </div>
    </div>
    <p class="formal-headline" role="status">{{ headline }}</p>
    <p v-if="requirementUnmet">形式化要求未满足；原答案仍保留。</p>
    <p v-else-if="verification.assessment?.status === 'met'">形式化要求已满足。</p>
    <p class="formal-boundary">LLM_REVIEWED 表示 LLM 整题审查通过；L1 表示有限工具检查；L2 表示形式目标通过内核与公理审计；L3 还要求独立规格对应审查。等级仅适用于已覆盖义务，不代表整题要求已满足。错误、超时和 unknown 不构成命题为假的反证。</p>
    <p v-if="effectiveGrade === 'L3' && reviewedCorrespondenceCount < correspondence.length" class="notice notice--warning" role="alert">L3 审查记录不完整；不能据此显示“原题已独立复核”。</p>

    <dl class="data-list">
      <template v-if="verification.assessment">
        <dt>证明范围</dt><dd>{{ verification.assessment.scope === 'original_problem' ? '原题范围' : '形式目标范围' }}（已覆盖义务）</dd>
        <dt>要求等级</dt><dd>{{ verification.assessment.required_grade }}</dd>
        <dt>已覆盖义务</dt><dd>{{ verification.assessment.covered_obligation_ids.join('、') || '无' }}</dd>
        <dt>要求判定原因</dt><dd>{{ verification.assessment.reason }}</dd>
      </template>
      <template v-else><dt>证明范围</dt><dd>形式目标；原题覆盖范围未报告</dd></template>
      <dt>Backend</dt><dd>{{ backend }}</dd>
      <dt>目标</dt><dd>{{ stringValue(target.lhs) && stringValue(target.rhs) ? `${stringValue(target.lhs)} = ${stringValue(target.rhs)}` : '未公开或不可用' }}</dd>
      <dt>环境</dt><dd>{{ stringValue(environment.lean_version) || '未知' }} · Mathlib {{ stringValue(environment.mathlib_version) || '未知' }}</dd>
      <dt>环境镜像</dt><dd>{{ stringValue(environment.image) || stringValue(environment.image_id) || stringValue(environment.image_digest) || '未知' }}</dd>
      <dt>工具链 / 模板</dt><dd>{{ stringValue(environment.toolchain) || '未知' }} · {{ stringValue(environment.template_version) || '未知' }}</dd>
      <dt>Manifest</dt><dd>{{ stringValue(environment.deployment_manifest_sha256) || stringValue(environment.manifest_digest) || '未知' }}</dd>
      <dt>策略哈希</dt><dd>{{ verification.policy_hash }}</dd>
      <dt>当前 attempt</dt><dd>{{ verification.current_attempt_id ?? '无' }}</dd>
      <dt>父 attempt</dt><dd>{{ parentAttemptId }}</dd>
      <dt>失败原因</dt><dd>{{ current?.reason ?? '无' }}</dd>
      <dt>累计成本</dt><dd>{{ numberValue(totalCost.elapsed_seconds) }} 秒 · {{ numberValue(totalCost.output_bytes) }} bytes<span v-if="totalCost.unknown === true"> · 消耗未知</span></dd>
      <dt>原题对应</dt><dd>原题对应{{ originalReviewLabel }}<span v-if="originalCorrespondence.record.review_record_hash"> · {{ originalCorrespondence.record.review_record_hash }}</span></dd>
      <dt>尝试 lineage</dt><dd>{{ attemptChain.length }} 个 attempt<span v-if="attemptChain.length"> · {{ attemptChain.join(' → ') }}</span></dd>
    </dl>

    <details v-if="verification.attempts.length">
      <summary>Attempt 历史（{{ verification.attempts.length }} 项）</summary>
      <ol class="formal-attempts">
        <li v-for="attempt in verification.attempts" :key="attempt.attempt_id">
          <span>{{ attemptLabel(attempt) }}</span>
          <span>父 attempt：{{ attempt.parent_attempt_id ?? '无' }}</span>
          <span v-if="attempt.reason">原因：{{ attempt.reason }}</span>
        </li>
      </ol>
    </details>

    <details>
      <summary>规格对应记录</summary>
      <dl class="data-list">
        <template v-for="item in correspondence" :key="item.key">
          <dt>{{ item.label }}</dt>
          <dd>{{ reviewStatus(item.record.review_status) }}<span v-if="item.record.review_record_hash"> · {{ item.record.review_record_hash }}</span></dd>
        </template>
      </dl>
    </details>

    <details v-if="current?.proof_artifact">
      <summary>ProofArtifact 摘要</summary>
      <dl class="data-list">
        <dt>Source hash</dt><dd>{{ stringValue(current.proof_artifact.source_hash) || '未知' }}</dd>
        <dt>Proof hash</dt><dd>{{ stringValue(current.proof_artifact.proof_hash) || '未知' }}</dd>
        <dt>Cleanup</dt><dd>{{ current.proof_artifact.cleanup_verified === true ? '已验证' : '未确认' }}</dd>
        <dt>Axioms</dt><dd>{{ Array.isArray(current.proof_artifact.axioms) ? current.proof_artifact.axioms.join('、') || '无' : '未知' }}</dd>
      </dl>
    </details>
  </section>
</template>
