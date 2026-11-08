<script setup lang="ts">
import type { RouteSummary } from '../api/routes.schemas'
defineProps<{ routes: RouteSummary }>()
const states: Record<string, string> = { created: '已登记', eligible: '可扩展', active: '执行中', stalled: '停滞', completed: '已结束', terminated: '已停止', pruned: '已淘汰' }
const ratingFields = [['verified_gain', '新增有效信用'], ['evidence_quality', '有效证据信用'], ['novelty', '新前沿目标'], ['cost', '已知 Token 消费'], ['http_attempts', 'HTTP 消费'], ['tool_calls', '工具消费'], ['wall_time_seconds', '耗时（秒）']] as const
</script>

<template>
  <section class="evidence-section" aria-label="串行路线与裁决">
    <h2>串行路线与裁决</h2>
    <p>路线决定搜索方向；最终答案仍需独立候选选择与整题审查。</p>
    <p>策略：{{ routes.policy_version }}</p>
    <p v-if="!routes.items.length">尚无已登记路线。</p>
    <ol>
      <li v-for="route in routes.items" :key="route.route_id">
        <strong>{{ route.kind === 'primary' ? '主路线' : '替代路线' }}</strong>
        · {{ states[route.status] }}<span v-if="route.needs_reevaluation"> · 证据变化，需重评</span>
        <details>
          <summary>路线身份与停止原因</summary>
          <dl class="data-list">
            <dt>路线</dt><dd>{{ route.route_id }}</dd>
            <dt>父路线</dt><dd>{{ route.parent_route_id ?? '无' }}</dd>
            <dt>前沿摘要</dt><dd>{{ route.frontier_digest }}</dd>
            <dt>停止原因</dt><dd>{{ route.stop_reason ?? route.elimination_reason ?? '尚无记录' }}</dd>
          </dl>
        </details>
      </li>
    </ol>
    <details v-for="rating in routes.evaluations ?? []" :key="rating.route_id">
      <summary>路线评分 · {{ rating.route_id }} · {{ rating.hard_gate ? '符合硬门槛' : '不符合当前门槛' }}</summary>
      <dl class="data-list">
        <template v-for="[key, label] in ratingFields" :key="key">
          <dt>{{ label }}</dt><dd>{{ rating.vector[key] ?? '未知' }}</dd>
        </template>
        <dt>输入摘要</dt><dd>{{ rating.input_hash }}</dd>
      </dl>
    </details>
    <details v-if="routes.budget">
      <summary>共享预算与收尾预留</summary>
      <p v-if="routes.budget.unknown">存在未决消费，保留未知预留，不按零成本处理。</p>
      <dl class="data-list">
        <template v-for="(value, key) in routes.budget.closing_reserve" :key="key">
          <dt>收尾预留 · {{ key }}</dt><dd>{{ value ?? '未知' }}</dd>
        </template>
      </dl>
    </details>
    <details v-for="(decision, index) in routes.decisions" :key="index">
      <summary>裁决 {{ index + 1 }} · {{ decision.reason ?? '原因未记录' }}</summary>
      <dl class="data-list">
        <dt>选中路线</dt><dd>{{ decision.selected_route_id ?? '无' }}</dd>
        <dt>Pareto 集</dt><dd>{{ decision.pareto_route_ids?.join('、') || '空' }}</dd>
        <dt>重放核验</dt><dd>{{ decision.replayable ? '已核验' : '尚未核验' }}</dd>
      </dl>
    </details>
  </section>
</template>
