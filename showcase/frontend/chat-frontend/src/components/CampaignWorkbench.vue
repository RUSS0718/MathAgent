<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { Campaign } from '../api/campaigns.schemas'
const items = ref<Awaited<ReturnType<typeof api.campaigns>>['campaigns']>([])
const detail = ref<Campaign | null>(null)
const notice = ref('')
const loading = ref(false)
const offset = ref(0)
function value(v: unknown): string { return v === null || v === undefined ? 'unknown（未知）' : typeof v === 'object' ? JSON.stringify(v) : String(v) }
async function load(id?: string): Promise<void> {
  loading.value = true; notice.value = ''
  try { if (id) detail.value = await api.campaign(id); else items.value = (await api.campaigns(offset.value)).campaigns }
  catch (error) { notice.value = error instanceof Error ? error.message : '报告不可用，请重试。' }
  finally { loading.value = false }
}
async function select(id: string): Promise<void> { globalThis.history.replaceState({}, '', '?campaign=' + encodeURIComponent(id)); await load(id) }
function download(): void { if (!detail.value) return; const url = URL.createObjectURL(new Blob([JSON.stringify(detail.value, null, 2)], { type: 'application/json' })); const link = document.createElement('a'); link.href = url; link.download = detail.value.campaign_id + '.json'; link.click(); URL.revokeObjectURL(url) }
onMounted(() => { const id = new URLSearchParams(globalThis.location.search).get('campaign'); void load(id ?? undefined) })
</script>
<template>
  <main class="campaign-workbench">
    <nav><a href="/dashboard">← 数学工作区</a> · <a href="/dashboard/campaigns">配对实验</a></nav>
    <h1>配对实验审阅</h1><p>来自持久报告。fake / replay 仅供工程演示；数学能力提升尚未评测。R1–R5：planned（计划中）。</p>
    <p role="status" v-if="loading">正在读取持久报告…</p><p role="alert" v-if="notice">{{ notice }}</p>
    <button type="button" :disabled="loading" @click="load(detail?.campaign_id)">刷新 / 重试</button>
    <template v-if="detail">
      <h2>{{ detail.campaign_id }}</h2><p>模式：<strong>{{ detail.mode }}</strong> · 状态：{{ detail.status }}（completed 仅表示全部终止）</p>
      <p>公共配置 hash：{{ detail.common_hash }}</p><p>配置身份：{{ detail.config_hash }}</p>
      <p v-if="detail.summary">完成 {{ detail.summary.completed_pairs }} / {{ detail.summary.total_pairs }} · 双臂成功 {{ detail.summary.successful_pairs }}（非正确率）</p>
      <button type="button" @click="download">导出当前公开报告 JSON</button>
      <p v-if="detail.archive">归档 SHA-256：{{ detail.archive.sha256 }}</p>
      <section v-for="pair in detail.pairs" :key="pair.pair_id" class="report-section">
        <h2>Pair {{ pair.pair_id }}</h2><p>题目 hash：{{ pair.problem_hash }}</p>
        <div class="campaign-arms"><article v-for="name in (['baseline', 'candidate'] as const)" :key="name">
          <h3>{{ name === 'baseline' ? 'baseline · 基线' : 'candidate · 候选' }}</h3>
          <dl><dt>运行状态</dt><dd>{{ pair.arms[name].status }}</dd><dt>质量 / 验证</dt><dd>{{ pair.arms[name].quality.status }}</dd><dt>失败类别</dt><dd>{{ pair.arms[name].error ?? '无已知失败' }}</dd><dt>HTTP attempts</dt><dd>{{ value(pair.arms[name].usage.http_attempts) }}</dd><dt>未知 attempts</dt><dd>{{ value(pair.arms[name].usage.unknown_attempts) }}</dd><dt>Provider 已知用量</dt><dd>{{ value(pair.arms[name].usage.provider_known) }}</dd><dt>Provider 未知字段</dt><dd>{{ value(pair.arms[name].usage.provider_unknown_fields) }}</dd><dt>时延（秒）</dt><dd>{{ value(pair.arms[name].latency_seconds) }}</dd><dt>金额</dt><dd>{{ value(pair.arms[name].cost) }}</dd><dt>请求 / 返回模型</dt><dd>{{ pair.arms[name].requested_model ?? 'unknown' }} / {{ pair.arms[name].returned_models?.join(', ') || 'unknown' }}</dd><dt>策略应用</dt><dd>{{ pair.arms[name].strategy_status ?? 'unknown' }}</dd></dl>
          <a v-if="pair.arms[name].job_id" :href="'/dashboard/run/' + pair.arms[name].job_id">审阅子 Run / Evidence →</a><p v-else>incomplete：尚无子 Run，不自动补跑。</p>
        </article></div>
      </section>
    </template>
    <template v-else><p v-if="!loading && !notice && !items.length">暂无持久批次。通过 campaign CLI 显式创建离线批次。</p><section v-for="item in items" :key="item.campaign_id" class="report-section"><button type="button" @click="select(item.campaign_id)">{{ item.campaign_id }}</button><p>{{ item.mode }} · {{ item.status }} · 完成 {{ item.summary?.completed_pairs }} / {{ item.summary?.total_pairs }}</p></section><button :disabled="offset === 0 || loading" @click="offset -= 20; load()">上一页</button><button :disabled="items.length < 20 || loading" @click="offset += 20; load()">下一页</button></template>
  </main>
</template>
<style scoped>
.campaign-workbench { max-width: 1100px; margin: auto; padding: 24px; overflow-wrap: anywhere; }
.campaign-workbench button { margin: 8px; padding: 8px 12px; }
.campaign-arms { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px; }
dl { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; } dd { margin: 0; }
@media (max-width: 700px) { .campaign-arms { grid-template-columns: 1fr; } }
</style>

