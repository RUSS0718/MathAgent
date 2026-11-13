<script setup lang="ts">
/** Display persisted intervention receipts without starting or resuming work. */
import { computed } from 'vue'
import { z } from 'zod'

const props = defineProps<{ value?: unknown }>()
const schema = z.object({
  status: z.enum(['deciding', 'reserved', 'completed', 'incomplete', 'interrupted', 'needs_review', 'skipped', 'canceled']),
  reason: z.string().nullable().optional(), pair_id: z.string().nullable().optional(),
  continuation: z.string().optional(),
  decision: z.object({ reason: z.string().optional(), hypothesis: z.string().optional(), method_id: z.string().optional() }).nullable().optional(),
  adoptions: z.array(z.object({
    status: z.enum(['adopted', 'rejected']), reason: z.string(), evidence_grade: z.string().nullable(),
    reference: z.object({ pair_id: z.string(), arm: z.string(), source_version: z.string(), scope: z.string() }),
  })).default([]),
})
const receipt = computed(() => {
  const parsed = schema.safeParse(props.value)
  return parsed.success ? parsed.data : null
})
const labels = {
  deciding: '选择干预', reserved: '执行分臂', completed: '分臂已完成', incomplete: '分臂未完成',
  interrupted: '执行中断', needs_review: '等待复核', skipped: '未执行干预', canceled: '干预已取消',
}
const reasons: Record<string, string> = {
  applicable_reviewed_result: '前提、范围、版本及依赖核对通过',
  source_version_changed: '来源版本已变化', premise_or_version_changed: '题意或版本已变化',
  scope_changed: '适用范围已变化', premises_changed: '前提已变化', dependencies_changed: '依赖已变化',
  source_review_not_verified: '来源核验未通过', result_source_missing: '来源不可用',
}
</script>

<template>
  <section v-if="receipt" class="serial-intervention" aria-label="串行自主干预" aria-live="polite">
    <h3>串行自主干预 · {{ labels[receipt.status] }} <small>实验性</small></h3>
    <p v-if="receipt.decision?.reason">{{ receipt.decision.reason }}</p>
    <p v-if="receipt.decision?.hypothesis">干预假设：{{ receipt.decision.hypothesis }}</p>
    <p v-if="receipt.reason">{{ reasons[receipt.reason] ?? receipt.reason }}</p>
    <details v-if="receipt.pair_id || receipt.adoptions.length">
      <summary>成果来源与采用记录</summary>
      <p v-if="receipt.pair_id">配对：{{ receipt.pair_id }}</p>
      <article v-for="(item, index) in receipt.adoptions" :key="index">
        <p>{{ item.status === 'adopted' ? '已采用' : '未采用' }} · {{ reasons[item.reason] ?? item.reason }}</p>
        <p>来源 {{ item.reference.pair_id }} · {{ item.reference.arm === 'intervention' ? '干预臂' : '控制臂' }} · {{ item.reference.scope }}</p>
        <p>来源版本 {{ item.reference.source_version }}</p>
        <p>原证据等级：{{ item.evidence_grade ?? '未取得' }}</p>
      </article>
    </details>
    <p v-if="receipt.status === 'needs_review'">未知结果保留原预留，等待显式复核。</p>
    <p v-else-if="receipt.continuation === 'main_task_continues'">主任务继续，沿用原预算与截止时间；完整答案仍须整题审查。</p>
  </section>
</template>

<style scoped>
.serial-intervention { min-width: 0; overflow-wrap: anywhere; }
.serial-intervention article { border-top: 1px solid var(--border); padding-block: var(--space-2); }
.serial-intervention small { color: var(--muted); }
</style>
