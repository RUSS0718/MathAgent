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
import PageFrame from './ui/PageFrame.vue'
import UiButton from './ui/UiButton.vue'
import UiIcon from './ui/UiIcon.vue'
import StatusBadge from './ui/StatusBadge.vue'
const props = defineProps<{ jobId: string }>()
const jobs = useJobsStore()
const controller = new JobController(jobs)
const job = computed(() => jobs.byId(props.jobId))
const report = ref<JobReport | null>(null)
const notice = ref('')
const connected = ref(false)
const cancelKey = createIdempotencyKey()
const busy = ref(false)
const loading = ref(true)
const fields = ['attempt_id', 'logical_call_id', 'attempt_index', 'started_at_utc', 'dispatch_status', 'action', 'requested_model', 'returned_model', 'status', 'http_status', 'finish_reason', 'duration_seconds', 'error_category', 'stop_category', 'metering_status', 'usage_source', 'usage']
const toolFields = ['name', 'tool_call_id', 'protocol', 'transport_mode', 'status', 'error_category', 'continuation_status', 'continuation_tool_call_id', 'continuation_response_received', 'candidate_status', 'coverage_status', 'result_summary', 'limitations']
function display(value: unknown): string { return value === null || value === undefined ? 'unknown（未知）' : typeof value === 'object' ? JSON.stringify(value) : String(value) }
async function refresh(): Promise<void> { loading.value = true; try { jobs.observe(await api.getJob(props.jobId)); report.value = await api.jobReport(props.jobId); notice.value = '' } catch (error) { notice.value = error instanceof Error ? error.message : '报告 unavailable（不可用）' } finally { loading.value = false } }
async function reconnect(): Promise<void> { await refresh(); connected.value = true; await controller.subscribe(props.jobId); connected.value = false; await refresh() }
async function exportEvidence(): Promise<void> { try { const evidence = await api.evidence(props.jobId); downloadJson(props.jobId + '-evidence.json', evidence); notice.value = '已导出持久公开 Evidence JSON。' } catch (error) { notice.value = error instanceof Error ? error.message : 'Evidence 导出失败，请重试。' } }
async function cancel(): Promise<void> { busy.value = true; try { await api.cancelJob(props.jobId, cancelKey); await refresh(); notice.value = '取消已记录；在途远端请求费用可能未知。' } catch (error) { notice.value = error instanceof Error ? error.message : '取消失败' } finally { busy.value = false } }
onMounted(() => { void reconnect() })
onUnmounted(() => controller.stopAll())
</script>
<template>
  <PageFrame title="子 Run 审阅" description="查看公开答案、最终验证范围与脱敏执行记录。" active="run">
    <template #actions><UiButton @click="exportEvidence"><UiIcon name="download" />导出公开 Evidence JSON</UiButton></template>
    <p class="record-id">{{ jobId }}</p>
    <div class="review-meta"><StatusBadge :value="report?.mode ?? 'unavailable'" /><StatusBadge :value="job?.status ?? 'unknown'" /><span class="muted">事件流：{{ connected ? '已连接 / 读取中' : '已结束或断开，可重连' }}</span></div>
    <p class="notice notice--warning">fake / replay 只证明工程演示。planned 表示尚未实现；unavailable 表示当前不可用。</p>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p><p v-if="job?.error" class="notice notice--error" role="alert">运行类别：{{ job.error }}</p>
    <div class="action-row"><UiButton :busy="loading" @click="refresh"><UiIcon name="refresh" />刷新持久报告</UiButton><UiButton :disabled="connected || loading" @click="reconnect">重连事件（沿用游标）</UiButton><UiButton variant="danger" :disabled="busy || !job || ['succeeded', 'failed', 'canceled'].includes(job.status)" @click="cancel">取消 Run</UiButton></div>
    <ReportSection v-if="report" :mode="report.mode" :status="report.status" :report="report.report" />
    <div v-else-if="loading" class="loading-state" role="status" aria-busy="true">正在读取运行报告…<div v-for="n in 3" :key="n" class="skeleton"></div></div>
    <section v-else class="empty-state"><h2>报告当前不可用</h2><p>请刷新重试，尚不能判断运行成功。</p></section>
    <template v-if="report">
      <section class="evidence-section"><h2>最终验证范围</h2><p>候选检查通过不等于完整解集证明。</p><dl class="data-list"><template v-for="field in ['status', 'scope', 'checker', 'checker_version', 'acceptance', 'binding', 'artifact', 'candidate_status', 'coverage_status', 'limitations', 'findings']" :key="field"><dt>{{ field }}</dt><dd>{{ display(report.report.checks[field]) }}</dd></template></dl></section>
      <section class="evidence-section"><h2>脱敏 Request Attempts</h2><p>reserved_dispatch_unconfirmed：本地预留已提交，远端是否接收或计费尚未确认；transport_observed 表示本地传输返回了观测。</p><p v-if="!report.report.request_attempts.length">无已记录 HTTP attempt；详见预算与计量。</p><details v-for="(attempt, index) in report.report.request_attempts" :key="index"><summary>Attempt {{ index + 1 }} · {{ display(attempt.status) }}</summary><dl class="data-list"><template v-for="field in fields" :key="field"><dt>{{ field }}</dt><dd>{{ display(attempt[field]) }}</dd></template></dl></details></section>
      <section class="evidence-section"><h2>工具闭环</h2><p v-if="!report.report.tool_summaries.length">无已记录工具结果。</p><article v-for="(tool, index) in report.report.tool_summaries" :key="index"><p v-if="tool.domain_status === 'out_of_domain'" class="notice notice--warning" role="status"><strong>域外：候选不满足定义域，最终结论仍为 unknown。</strong></p><dl class="data-list"><template v-for="field in toolFields" :key="field"><dt>{{ field }}</dt><dd>{{ display(tool[field]) }}</dd></template></dl></article></section>
    </template>
    <AgentTimeline v-if="job" :events="job.events" />
  </PageFrame>
</template>
