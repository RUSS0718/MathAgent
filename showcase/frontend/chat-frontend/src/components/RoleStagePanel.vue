<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { api } from '../api/client'
import type { RoleStage } from '../api/role-stage.schemas'
import { roleLabels, statusLabels } from '../runtime/jobs/causal-progress'
import { renderSafeMarkdown } from '../renderers/markdown-adapter'

const props = defineProps<{ jobId?: string; role: string; source?: string; jobStatus: string; runtimeState?: string }>()
const emit = defineEmits<{ filter: [role: string] }>()
const dialog = ref<HTMLDialogElement>()
const content = ref<RoleStage | null>(null)
const loading = ref(false)
const failed = ref(false)
let request = 0
watch(() => [props.jobId, props.role, props.source], () => { request++; dialog.value?.close(); content.value = null })
async function open() {
  const id = ++request
  content.value = null
  loading.value = true
  failed.value = false
  await nextTick()
  if (!dialog.value?.open) dialog.value?.showModal()
  try {
    const result = props.jobId ? await api.roleResults(props.jobId, props.role, props.source) : null
    if (id === request && result && result.job_id === props.jobId && result.role === props.role) content.value = result
  } catch { if (id === request) failed.value = true }
  finally { if (id === request) loading.value = false }
}
defineExpose({ open })
</script>

<template>
  <dialog ref="dialog" aria-labelledby="role-stage-heading">
    <form method="dialog"><button autofocus>关闭</button></form>
    <h2 id="role-stage-heading">{{ roleLabels[role] }}阶段成果</h2>
    <p>任务：{{ statusLabels[jobStatus] ?? '状态待确认' }} · 角色：{{ ({ idle: '未参与', running: '执行中', completed: '已完成', failed: '遇到问题', unknown: '结果未知' } as Record<string, string>)[runtimeState ?? 'unknown'] ?? '状态待确认' }}</p>
    <p>{{ role === 'planner' ? '职责：安排求解目标、方法和步骤依赖。' : '职责：组织阶段安排与任务派发；协调安排不是数学推导。' }}</p>
    <p v-if="loading" role="status">正在读取已保存成果…</p>
    <p v-else-if="failed" role="alert">读取失败，最新状态未确认。</p>
    <p v-else-if="!content?.results.length">来源无法确认，成果暂不可用。</p>
    <section v-for="result in content?.results ?? []" :key="result.source_ref" data-plan-body>
      <h3>计划第 {{ result.plan_version }} 版 · 阶段安排</h3>
      <p>{{ result.validity === 'current' ? '当前版本有效' : '已替换' }}</p>
      <p>检查范围：计划结构校验通过，不代表目标已完成。</p>
      <ol><li v-for="item in result.items" :key="item.label">
        <h4>{{ item.label }} · {{ item.title }}</h4><div v-html="renderSafeMarkdown(item.objective)" />
        <p>先后依赖：{{ item.depends_on.join('、') || '无前置步骤' }}</p>
      </li></ol>
    </section>
    <button v-if="failed" type="button" @click="open">重试读取</button>
    <button type="button" @click="emit('filter', role); dialog?.close()">只看该角色</button>
  </dialog>
</template>

<style scoped>
dialog { margin: 0 0 0 auto; width: min(560px, 80vw); height: 100dvh; max-height: 100dvh; padding: 24px; border: 1px solid var(--border); background: var(--surface); color: var(--text); overflow-y: auto; }
dialog:modal, dialog::backdrop { overscroll-behavior: contain; }
dialog::backdrop { overflow: hidden; background: #0005; }
form { float: right; }
p { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.65; }
button { padding: 8px 12px; background: var(--surface); color: var(--text); border: 1px solid var(--border-strong); cursor: pointer; }
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
