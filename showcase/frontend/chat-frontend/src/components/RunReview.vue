<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api/client'
import { downloadJson } from '../runtime/reports/download'
import type { JobReport } from '../api/reports.schemas'
import { useJobsStore } from '../stores/jobs.store'
import { JobController } from '../runtime/jobs/job-controller'
import { createIdempotencyKey } from '../runtime/jobs/idempotency'
import AgentTimeline from './AgentTimeline.vue'
import ReportSection from './ReportSection.vue'
const props = defineProps<{ jobId: string }>()
const jobs = useJobsStore()
const controller = new JobController(jobs)
const job = computed(() => jobs.byId(props.jobId))
const report = ref<JobReport | null>(null)
const notice = ref('')
const connected = ref(false)
const cancelKey = createIdempotencyKey()
const busy = ref(false)
const fields = ['attempt_id', 'logical_call_id', 'attempt_index', 'action', 'requested_model', 'returned_model', 'status', 'http_status', 'finish_reason', 'duration_seconds', 'error_category', 'stop_category', 'metering_status', 'usage_source', 'usage']
const toolFields = ['name', 'tool_call_id', 'protocol', 'transport_mode', 'status', 'error_category', 'continuation_status', 'continuation_tool_call_id', 'continuation_response_received', 'candidate_status', 'coverage_status', 'result_summary', 'limitations']
function display(value: unknown): string { return value === null || value === undefined ? 'unknown（未知）' : typeof value === 'object' ? JSON.stringify(value) : String(value) }
async function refresh(): Promise<void> { try { jobs.observe(await api.getJob(props.jobId)); report.value = await api.jobReport(props.jobId); notice.value = '' } catch (error) { notice.value = error instanceof Error ? error.message : '报告 unavailable（不可用）' } }
async function reconnect(): Promise<void> { await refresh(); connected.value = true; await controller.subscribe(props.jobId); connected.value = false; await refresh() }
async function exportEvidence(): Promise<void> { try { const evidence = await api.evidence(props.jobId); downloadJson(props.jobId + '-evidence.json', evidence); notice.value = '已导出持久公开 Evidence JSON。' } catch (error) { notice.value = error instanceof Error ? error.message : 'Evidence 导出失败，请重试。' } }
async function cancel(): Promise<void> { busy.value = true; try { await api.cancelJob(props.jobId, cancelKey); await refresh(); notice.value = '取消已记录；在途远端请求费用可能未知。' } catch (error) { notice.value = error instanceof Error ? error.message : '取消失败' } finally { busy.value = false } }
onMounted(() => { void reconnect() })
onUnmounted(() => controller.stopAll())
</script>
<template>
  <main class="run-review">
    <nav><a href="/dashboard/campaigns">← 配对实验</a> · <a href="/dashboard">数学工作区</a></nav><h1>子 Run 审阅</h1><p>{{ jobId }}</p>
    <p>模式：<strong>{{ report?.mode ?? 'unavailable' }}</strong> · Job：{{ job?.status ?? 'unknown' }} · 事件流：{{ connected ? '已连接 / 读取中' : '已结束或断开，可重连' }}</p>
    <p>fake / replay 只证明工程演示。planned 表示尚未实现；unavailable 表示当前不可用。</p>
    <p v-if="notice" role="alert">{{ notice }}</p><p v-if="job?.error" role="alert">运行类别：{{ job.error }}</p>
    <button @click="refresh">刷新持久报告</button><button @click="reconnect">重连事件（沿用游标）</button><button :disabled="busy || !job || ['succeeded', 'failed', 'canceled'].includes(job.status)" @click="cancel">取消 Run</button>
    <button type="button" @click="exportEvidence">导出公开 Evidence JSON</button>
    <ReportSection v-if="report" :mode="report.mode" :status="report.status" :report="report.report" />
    <p v-else role="status">报告 unavailable；请刷新重试，尚不能判断运行成功。</p>
    <section v-if="report" class="report-section"><h2>最终验证范围</h2><dl><template v-for="field in ['status', 'scope', 'checker', 'checker_version', 'acceptance', 'binding', 'artifact', 'candidate_status', 'coverage_status', 'limitations', 'findings']" :key="field"><dt>{{ field }}</dt><dd>{{ display(report.report.checks[field]) }}</dd></template></dl><p>候选检查通过不等于完整解集证明。</p>
      <h2>脱敏 Request Attempts</h2><p v-if="!report.report.request_attempts.length">无已记录 HTTP attempt；详见预算与计量。</p><details v-for="(attempt, index) in report.report.request_attempts" :key="index"><summary>Attempt {{ index + 1 }} · {{ display(attempt.status) }}</summary><dl><template v-for="field in fields" :key="field"><dt>{{ field }}</dt><dd>{{ display(attempt[field]) }}</dd></template></dl></details>
      <h2>工具闭环</h2><p v-if="!report.report.tool_summaries.length">无已记录工具结果。</p><article v-for="(tool, index) in report.report.tool_summaries" :key="index"><p v-if="tool.domain_status === 'out_of_domain'" role="status"><strong>域外：候选不满足定义域，最终结论仍为 unknown。</strong></p><dl><template v-for="field in toolFields" :key="field"><dt>{{ field }}</dt><dd>{{ display(tool[field]) }}</dd></template></dl></article>
    </section>
    <AgentTimeline v-if="job" :events="job.events" />
  </main>
</template>
<style scoped>
.run-review { max-width: 1000px; margin: auto; padding: 24px; overflow-wrap: anywhere; } button, a { margin-right: 12px; } button { padding: 8px; } dl { display: grid; grid-template-columns: minmax(130px, 1fr) 2fr; gap: 8px; } dd { margin: 0; } summary { cursor: pointer; padding: 10px 0; }
</style>


