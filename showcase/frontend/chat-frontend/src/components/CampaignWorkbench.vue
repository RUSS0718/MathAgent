<script setup lang="ts">
/** Read persisted experiment reports without starting or repairing experiments. */
import { onMounted, ref } from 'vue'
import { api } from '../api/client'
import { downloadJson } from '../runtime/reports/download'
import type { Campaign } from '../api/campaigns.schemas'
import PageFrame from './ui/PageFrame.vue'
import UiButton from './ui/UiButton.vue'
import UiIcon from './ui/UiIcon.vue'
import StatusBadge from './ui/StatusBadge.vue'
const items = ref<Awaited<ReturnType<typeof api.campaigns>>['campaigns']>([])
const detail = ref<Campaign | null>(null)
const selectedId = ref(new URLSearchParams(globalThis.location.search).get('campaign'))
const notice = ref('')
const loading = ref(false)
const offset = ref(0)
function value(v: unknown): string { return v === null || v === undefined ? 'unknown（未知）' : typeof v === 'object' ? JSON.stringify(v) : String(v) }
async function load(): Promise<void> {
  loading.value = true; notice.value = ''
  try { if (selectedId.value) detail.value = await api.campaign(selectedId.value); else items.value = (await api.campaigns(offset.value)).campaigns }
  catch (error) { notice.value = error instanceof Error ? error.message : '报告不可用，请重试。' }
  finally { loading.value = false }
}
async function select(id: string): Promise<void> { selectedId.value = id; detail.value = null; globalThis.history.replaceState({}, '', '?campaign=' + encodeURIComponent(id)); await load() }
async function back(): Promise<void> { selectedId.value = null; detail.value = null; globalThis.history.replaceState({}, '', globalThis.location.pathname); await load() }
function download(): void { if (detail.value) downloadJson(detail.value.campaign_id + '.json', detail.value) }
onMounted(load)
</script>

<template>
  <PageFrame title="配对实验审阅" description="对照基线与候选运行，查看用量、失败类别和验证边界。" active="campaigns">
    <template #actions><UiButton :busy="loading" @click="load"><UiIcon name="refresh" />刷新 / 重试</UiButton></template>
    <p class="notice notice--warning">来自持久报告。fake / replay 仅供工程演示；数学能力提升尚未评测。R1–R5：planned（计划中）。</p>
    <p v-if="notice" class="notice notice--error" role="alert">{{ notice }} 请刷新重试。</p>
    <div v-if="selectedId" class="review-toolbar"><UiButton variant="ghost" @click="back">返回批次列表</UiButton><UiButton v-if="detail" @click="download"><UiIcon name="download" />导出当前公开报告 JSON</UiButton></div>
    <div v-if="loading" class="loading-state" role="status" aria-busy="true">正在读取持久报告…<div v-for="n in 3" :key="n" class="skeleton"></div></div>
    <div v-else-if="detail" class="campaign-detail">
      <h2>{{ detail.campaign_id }}</h2>
      <div class="review-meta"><StatusBadge :value="detail.mode" /><StatusBadge :value="detail.status" /><span class="muted">completed 仅表示全部终止</span></div>
      <p v-if="detail.summary">完成 {{ detail.summary.completed_pairs }} / {{ detail.summary.total_pairs }} · 双臂成功 {{ detail.summary.successful_pairs }}（非正确率）</p>
      <details class="evidence-section"><summary>配置与归档身份</summary><dl class="data-list"><dt>公共配置 hash</dt><dd class="record-id">{{ detail.common_hash }}</dd><dt>配置身份</dt><dd class="record-id">{{ detail.config_hash ?? 'unknown' }}</dd><template v-if="detail.archive"><dt>归档 SHA-256</dt><dd class="record-id">{{ detail.archive.sha256 }}</dd></template></dl></details>
      <section v-for="pair in detail.pairs" :key="pair.pair_id" class="report-section">
        <h2>Pair {{ pair.pair_id }}</h2><p class="record-id">题目 hash：{{ pair.problem_hash }}</p>
        <div class="campaign-arms"><article v-for="name in (['baseline', 'candidate'] as const)" :key="name">
          <h3>{{ name === 'baseline' ? 'baseline · 基线' : 'candidate · 候选' }}</h3>
          <dl class="data-list">
            <dt>运行状态</dt><dd><StatusBadge :value="pair.arms[name].status" /></dd>
            <dt>质量 / 验证</dt><dd>{{ pair.arms[name].quality.status }}</dd>
            <dt>失败类别</dt><dd>{{ pair.arms[name].error ?? '无已知失败' }}</dd>
            <dt>HTTP attempts</dt><dd>{{ value(pair.arms[name].usage.http_attempts) }}</dd>
            <dt>未知 attempts</dt><dd>{{ value(pair.arms[name].usage.unknown_attempts) }}</dd>
            <dt>Provider 已知用量</dt><dd>{{ value(pair.arms[name].usage.provider_known) }}</dd>
            <dt>Provider 未知字段</dt><dd>{{ value(pair.arms[name].usage.provider_unknown_fields) }}</dd>
            <dt>时延（秒）</dt><dd>{{ value(pair.arms[name].latency_seconds) }}</dd>
            <dt>金额</dt><dd>{{ value(pair.arms[name].cost) }}</dd>
            <dt>请求 / 返回模型</dt><dd>{{ pair.arms[name].requested_model ?? 'unknown' }} / {{ pair.arms[name].returned_models?.join(', ') || 'unknown' }}</dd>
            <dt>策略应用</dt><dd>{{ pair.arms[name].strategy_status ?? 'unknown' }}</dd>
          </dl>
          <a v-if="pair.arms[name].job_id" class="ui-button" :href="'/dashboard/run/' + pair.arms[name].job_id">审阅子 Run / Evidence<UiIcon name="arrowRight" /></a><p v-else class="notice">incomplete：尚无子 Run，不自动补跑。</p>
        </article></div>
      </section>
    </div>
    <template v-else-if="!selectedId">
      <section v-if="!notice && !items.length" class="empty-state"><UiIcon name="experiments" /><h2>暂无持久批次</h2><p>通过 campaign CLI 显式创建离线批次后，在这里比较基线与候选。当前页面不会自动补跑实验。</p></section>
      <div v-else class="campaign-list"><article v-for="item in items" :key="item.campaign_id" class="campaign-row"><div><h2><button class="text-button" @click="select(item.campaign_id)">{{ item.campaign_id }}</button></h2><div class="review-meta"><StatusBadge :value="item.mode" /><StatusBadge :value="item.status" /></div><p>完成 {{ item.summary?.completed_pairs ?? '未知' }} / {{ item.summary?.total_pairs ?? '未知' }}</p></div><UiButton icon-only :aria-label="`审阅 ${item.campaign_id}`" @click="select(item.campaign_id)"><UiIcon name="arrowRight" /></UiButton></article></div>
      <nav class="pagination" aria-label="批次分页"><span>第 {{ offset / 20 + 1 }} 页</span><UiButton :disabled="offset === 0 || loading" @click="offset -= 20; load()">上一页</UiButton><UiButton :disabled="items.length < 20 || loading" @click="offset += 20; load()">下一页</UiButton></nav>
    </template>
  </PageFrame>
</template>
