<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { api } from '../api/client'
import type { GoalCacheResponse } from '../api/goal-cache.schemas'
import { isApiError } from '../api/errors'
import UiButton from './ui/UiButton.vue'

const props = defineProps<{ sessionId: string }>()
type CacheView = { status: 'loading' | 'unavailable' | 'error' } | { status: 'available'; data: GoalCacheResponse }
const view = ref<CacheView>({ status: 'loading' })
const pending = ref<'enable' | 'disable' | 'clear' | ''>('')
const error = ref('')
const success = ref('')
let generation = 0

async function load(): Promise<void> {
  const current = ++generation
  error.value = ''
  view.value = { status: 'loading' }
  try {
    const data = await api.goalCache(props.sessionId)
    if (current === generation) view.value = { status: 'available', data }
  } catch (cause) {
    if (current !== generation) return
    if (isApiError(cause) && cause.status === 404) view.value = { status: 'unavailable' }
    else { view.value = { status: 'error' }; error.value = cause instanceof Error ? cause.message : '全局目标缓存暂时无法读取。' }
  }
}

async function update(enabled: boolean): Promise<void> {
  pending.value = enabled ? 'enable' : 'disable'
  error.value = ''
  success.value = ''
  try {
    await api.setGoalCacheEnabled(props.sessionId, enabled)
    const data = await api.goalCache(props.sessionId)
    view.value = { status: 'available', data }
    success.value = enabled ? '全局目标缓存已启用。' : '全局目标缓存已停用。'
  } catch (cause) { handleMutationError(cause) }
  finally { pending.value = '' }
}

async function clear(): Promise<void> {
  if (!globalThis.confirm('确认清除全局目标缓存？此操作无法撤销。')) return
  pending.value = 'clear'
  error.value = ''
  success.value = ''
  try {
    await api.clearGoalCache(props.sessionId)
    const data = await api.goalCache(props.sessionId)
    view.value = { status: 'available', data }
    success.value = '清除操作已记录；下方显示服务端返回的缓存状态与审计历史。'
  } catch (cause) { handleMutationError(cause) }
  finally { pending.value = '' }
}

function handleMutationError(cause: unknown): void {
  if (isApiError(cause) && cause.status === 404) view.value = { status: 'unavailable' }
  error.value = cause instanceof Error ? cause.message : '操作失败，请重试。'
}

watch(() => props.sessionId, () => { success.value = ''; void load() }, { immediate: true })
onUnmounted(() => { generation += 1 })
</script>

<template>
  <section v-if="view.status !== 'unavailable'" class="evidence-section" aria-label="会话形式缓存" :aria-busy="view.status === 'loading' || Boolean(pending) ? 'true' : undefined">
    <h2>会话形式缓存</h2>
    <p>缓存按当前会话隔离。重用前会在当前 Lean 环境重新核验；缓存元数据不是证明，也不作为数学证据。</p>
    <p v-if="view.status === 'loading'" role="status" aria-busy="true">正在读取全局目标缓存…</p>
    <div v-else-if="view.status === 'error'" class="notice notice--warning" role="alert">
      {{ error }} <UiButton :disabled="Boolean(pending)" @click="load">重试读取</UiButton>
    </div>
    <template v-else-if="view.status === 'available'">
      <p role="status">当前状态：{{ view.data.enabled ? '已启用' : '已停用' }}</p>
      <div class="action-row">
        <UiButton v-if="!view.data.enabled" variant="primary" :busy="pending === 'enable'" :disabled="Boolean(pending)" @click="update(true)">启用本会话缓存</UiButton>
        <UiButton v-else :busy="pending === 'disable'" :disabled="Boolean(pending)" @click="update(false)">停用本会话缓存</UiButton>
        <UiButton variant="danger" :busy="pending === 'clear'" :disabled="Boolean(pending)" @click="clear">清除本会话缓存</UiButton>
      </div>
      <p v-if="error" class="notice notice--error" role="alert">{{ error }}</p>
      <p v-if="success" role="status" aria-live="polite">{{ success }}</p>
      <h3>缓存条目</h3>
      <p v-if="!view.data.entries.length" class="muted" role="status">当前没有缓存条目。</p>
      <article v-for="entry in view.data.entries" :key="entry.cache_id">
        <dl class="data-list">
          <dt>缓存 ID</dt><dd>{{ entry.cache_id }}</dd>
          <dt>生命周期状态</dt><dd>{{ entry.state }}</dd>
          <template v-if="entry.reason"><dt>原因</dt><dd>{{ entry.reason }}</dd></template>
          <template v-if="entry.source_run_id"><dt>来源 Run</dt><dd>{{ entry.source_run_id }}</dd></template>
          <template v-if="entry.source_attempt_id"><dt>来源 Attempt</dt><dd>{{ entry.source_attempt_id }}</dd></template>
          <template v-if="entry.source_grade"><dt>来源等级</dt><dd>{{ entry.source_grade }}</dd></template>
          <template v-if="entry.grade_ceiling"><dt>缓存等级上限</dt><dd>{{ entry.grade_ceiling }}</dd></template>
          <dt>创建时间</dt><dd><time :datetime="entry.created_at">{{ entry.created_at }}</time></dd>
          <dt>更新时间</dt><dd><time :datetime="entry.updated_at">{{ entry.updated_at }}</time></dd>
        </dl>
      </article>
      <h3>审计事件</h3>
      <p v-if="!view.data.events.length" class="muted" role="status">当前没有审计事件。</p>
      <ul v-else aria-label="全局目标缓存审计事件">
        <li v-for="(event, index) in view.data.events" :key="`${event.cache_id ?? ''}:${event.created_at}:${index}`">
          <span>{{ event.event }}</span><span v-if="event.cache_id"> · {{ event.cache_id }}</span>
          <span v-if="event.details?.category"> · {{ event.details.category }}</span>
          <span v-if="event.details?.reason"> · {{ event.details.reason }}</span>
          <span v-if="event.details?.source_run_id"> · 来源 Run {{ event.details.source_run_id }}</span>
          · <time :datetime="event.created_at">{{ event.created_at }}</time>
        </li>
      </ul>
    </template>
  </section>
</template>
