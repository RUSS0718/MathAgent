<script setup lang="ts">
import type { RouteSummary } from '../api/routes.schemas'
defineProps<{ routes: RouteSummary }>()
const states: Record<string, string> = { created: '已登记', eligible: '可扩展', active: '执行中', stalled: '停滞', completed: '已结束', terminated: '已停止', pruned: '已淘汰' }
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
