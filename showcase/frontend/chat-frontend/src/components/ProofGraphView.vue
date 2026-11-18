<script setup lang="ts">
import type { ProofGraph } from '../api/reports.schemas'
const props = defineProps<{ graph: ProofGraph; runId: string }>()
function nodeId(id: string): string {
  return `proof-${props.runId}-v${props.graph.graph_version}-${id}`
}
</script>

<template>
  <section class="evidence-section" aria-label="证明依赖图">
    <h2>证明依赖图 · 版本 {{ graph.graph_version }}</h2>
    <p>同一尝试的前提须全部成立（AND）；同一命题的独立有效支撑择一成立（OR）。模型审查不等于形式化证明。</p>
    <p v-if="!graph.propositions.length">本版本尚无可公开的命题节点。</p>
    <ol>
      <li v-for="node in graph.propositions" :id="nodeId(node.id)" :key="node.id">
        <a :href="`#${nodeId(node.id)}`">命题 {{ node.id }}</a>
        · {{ node.status }} · {{ node.grade ?? '待验证' }}
        <strong v-if="node.conflict"> · 冲突待审，不能作为前提</strong>
        <details>
          <summary>查看独立支撑与来源</summary>
          <ul>
            <li v-for="attempt in graph.attempts.filter(item => item.conclusion === node.id)" :key="attempt.id">
              尝试 {{ attempt.id }} · {{ attempt.direction }} · {{ attempt.status }} · {{ attempt.grade ?? '待验证' }}
              <span v-if="!attempt.dependencies.length"> · 无图内前提</span>
              <span v-else> · AND 前提：<a v-for="parent in attempt.dependencies" :key="parent" :href="`#${nodeId(parent)}`"> {{ parent }} </a></span>
              <p>来源：{{ attempt.sources.join('、') || '尚无有效来源' }}</p>
            </li>
          </ul>
        </details>
      </li>
    </ol>
  </section>
</template>
