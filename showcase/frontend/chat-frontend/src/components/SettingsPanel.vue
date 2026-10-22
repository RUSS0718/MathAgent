<script setup lang="ts">
/** Show only server-reported capabilities; no decorative or ineffective switches. */
import { onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { CapabilitiesResponse } from '../api/capabilities.schemas'
import PageFrame from './ui/PageFrame.vue'
import UiButton from './ui/UiButton.vue'
import UiIcon from './ui/UiIcon.vue'
import StatusBadge from './ui/StatusBadge.vue'
const capabilities = ref<CapabilitiesResponse | null>(null)
const loading = ref(true)
const error = ref('')
async function load(): Promise<void> {
  loading.value = true; error.value = ''
  try { capabilities.value = await api.capabilities() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '无法读取工作区设置，请重试。' }
  finally { loading.value = false }
}
onMounted(load)
</script>

<template>
  <PageFrame title="工作区设置" description="查看当前运行环境与可用能力。以下信息来自本机服务。" active="settings">
    <template #actions><UiButton :busy="loading" @click="load"><UiIcon name="refresh" />刷新状态</UiButton></template>
    <p v-if="error" class="notice notice--error" role="alert">{{ error }} 请刷新重试。</p>
    <div v-if="loading" class="loading-state" role="status" aria-busy="true">正在读取配置…<div v-for="n in 3" :key="n" class="skeleton"></div></div>
    <div v-else-if="capabilities" class="settings-sections">
      <section class="settings-section"><div><h2>运行环境</h2><p>当前为本机 Showcase 工作区。</p></div><dl class="data-list"><dt>配置</dt><dd>{{ capabilities.profile }}</dd><dt>执行模式</dt><dd><StatusBadge :value="capabilities.execution?.mode ?? 'unavailable'" /></dd><dt>模型服务</dt><dd>{{ capabilities.execution?.provider ?? '未提供' }}</dd><dt>配置状态</dt><dd>{{ capabilities.execution?.status ?? '未知' }}</dd></dl></section>
      <section class="settings-section"><div><h2>工作区能力</h2><p>功能是否启用由服务端决定。</p></div><dl class="data-list"><dt>任务执行</dt><dd>{{ capabilities.jobs.enabled ? '已启用' : '未启用' }}</dd><dt>实时事件</dt><dd>{{ capabilities.sse.enabled ? '已启用' : '未启用' }}</dd><dt>PNG 题图</dt><dd>{{ capabilities.files.upload.enabled ? '已启用' : '未启用' }}<p v-if="capabilities.files.upload.reason" class="muted">{{ capabilities.files.upload.reason }}</p></dd><dt>验证模式</dt><dd>{{ capabilities.verification_mode.join(' / ') || '未提供' }}</dd></dl></section>
      <section class="settings-section"><div><h2>报告与边界</h2><p>区分运行成功与数学结论。</p></div><div class="settings-copy"><p>fake / replay 用于工程演示，不代表真实模型能力。候选检查通过不等于完整解集证明。</p><p>公开报告只展示脱敏摘要。查看运行状态和验证范围后，可在子 Run 审阅页导出 Evidence。</p><a href="/dashboard/campaigns">查看配对实验与运行记录</a></div></section>
    </div>
  </PageFrame>
</template>
