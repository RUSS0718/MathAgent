<script setup lang="ts">
/** Accessible SVG projection of an existing public dependency-graph snapshot. */
import { computed, onMounted, ref } from 'vue'
import type { SystemRunResponse } from '../api/system.schemas'

const props = defineProps<{
  graph: NonNullable<SystemRunResponse['graph']>
  selectedNodeId?: string
  hrefForNode: (nodeId: string) => string
}>()
const startedAt = performance.now()
const renderMilliseconds = ref<number | null>(null)
const layout = computed(() => {
  const items = [...props.graph.propositions.map(node => ({ ...node, kind: 'proposition' })),
    ...props.graph.attempts.map(node => ({ ...node, conflict: false, kind: 'inference' }))]
  const columns = Math.max(1, Math.min(25, items.length))
  const nodes = items.map((node, index) => ({
    ...node,
    x: 44 + (index % columns) * 52,
    y: 34 + Math.floor(index / columns) * 48,
  }))
  const positions = new Map(nodes.map(node => [node.id, node]))
  const pairs = nodes.flatMap(node => node.dependencies.map(parent => ({ from: parent, to: node.id })))
  pairs.push(...props.graph.attempts.map(attempt => ({ from: attempt.id, to: attempt.conclusion })))
  const links = pairs.flatMap(pair => {
    const node = positions.get(pair.to)
    const target = positions.get(pair.from)
    return target && node ? [{ id: `${pair.from}-${node.id}`, x1: target.x, y1: target.y,
      x2: node.x, y2: node.y }] : []
  })
  return { nodes, links, width: Math.max(160, columns * 52 + 40), height: Math.max(96, Math.ceil(nodes.length / columns) * 48 + 28) }
})

function color(status: string): string {
  if (status === 'supported') return 'var(--accent)'
  if (status === 'refuted' || status === 'invalidated') return 'var(--danger, #a33)'
  return 'var(--border)'
}

onMounted(() => requestAnimationFrame(() => requestAnimationFrame(() => {
  renderMilliseconds.value = performance.now() - startedAt
})))
</script>

<template>
  <section class="f7-graph" aria-label="依赖图可视化">
    <p class="muted">图版本 {{ graph.graph_version }} · {{ graph.propositions.length }} 节点 · {{ graph.attempts.length }} 推导</p>
    <svg class="f7-graph__canvas" :viewBox="`0 0 ${layout.width} ${layout.height}`" role="group"
      :style="{ minWidth: `${Math.min(layout.width, 680)}px` }"
      :aria-label="`依赖图，共 ${graph.propositions.length} 个命题节点、${graph.attempts.length} 个推导节点`"
      :data-node-count="graph.propositions.length" :data-render-ms="renderMilliseconds ?? undefined">
      <defs><marker id="f7-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
        <path d="M0,0 L8,4 L0,8 z" fill="currentColor" />
      </marker></defs>
      <g class="f7-graph__edges" aria-hidden="true">
        <line v-for="link in layout.links" :key="link.id" :x1="link.x1" :y1="link.y1" :x2="link.x2" :y2="link.y2" />
      </g>
      <g v-for="node in layout.nodes" :key="node.id" class="f7-graph__node">
        <a :id="`f7-node-${encodeURIComponent(node.id)}`" :href="hrefForNode(node.id)" :aria-label="`节点 ${node.id}，${node.status}，${node.grade ?? '待验证'}`">
          <rect v-if="node.kind === 'inference'" :x="node.x - 15" :y="node.y - 15" width="30" height="30"
            :stroke="color(node.status)" :class="{ 'is-selected': node.id === selectedNodeId }" />
          <circle v-else :cx="node.x" :cy="node.y" r="15" :stroke="color(node.status)"
            :class="{ 'is-selected': node.id === selectedNodeId, 'has-conflict': node.conflict }" />
          <text :x="node.x" :y="node.y + 4">{{ node.id }}</text>
          <title>{{ node.id }} · {{ node.status }} · {{ node.grade ?? '待验证' }}</title>
        </a>
      </g>
    </svg>
    <ul class="f7-graph__accessible-list" aria-label="依赖图节点明细">
      <li v-for="node in layout.nodes" :key="node.id">
        <a :href="hrefForNode(node.id)">{{ node.id }}</a> · {{ node.status }} · {{ node.grade ?? '待验证' }}
        <span v-if="node.conflict"> · 冲突待审</span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.f7-graph { overflow:auto; max-width:100%; }
.f7-graph__canvas { display:block; width:100%; max-height:70vh; }
.f7-graph__edges line { stroke:var(--muted); stroke-width:1.25; marker-end:url(#f7-arrow); }
.f7-graph__node circle,.f7-graph__node rect { fill:var(--surface); stroke-width:2; }
.f7-graph__node .is-selected { stroke-width:4; }
.f7-graph__node circle.has-conflict { stroke-dasharray:3 2; }
.f7-graph__node text { fill:var(--text); text-anchor:middle; font-size:8px; }
.f7-graph__accessible-list { display:grid; grid-template-columns:repeat(auto-fit,minmax(9rem,1fr)); gap:.35rem .75rem; }
</style>
