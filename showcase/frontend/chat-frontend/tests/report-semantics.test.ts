import test from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { reportSchema } from '../src/api/reports.schemas.ts'
import { decodeSseBlock, SseProtocolError } from '../src/api/events.schemas.ts'
import { createPinia, setActivePinia } from 'pinia'
import { useJobsStore } from '../src/stores/jobs.store.ts'

test('existing report renders completed LLM review and binding without a mathematical pass', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const { default: ReportSection } = await server.ssrLoadModule('/src/components/ReportSection.vue')
    const report = reportSchema.parse({
      version: 'report-v0.2', evidence_id: 'run_test', status: 'COMPLETED', mode: 'star_limited',
      report: {
        answer: '1+1=2', public_summary: '受控回复', stage: 'terminal', tool_summaries: [],
        checks: { status: 'unknown', acceptance: 'needs_review', binding: 'same_artifact' },
        limitations: [],
        semantics: {
          version: 'star-result-semantics-v1', execution: 'completed', transport: 'known',
          whole_review: 'accepted', binding: 'same_artifact', formal_verification: 'not_verified',
        },
      },
    })
    const html = await renderToString(createSSRApp(ReportSection, { report: report.report }))
    assert.match(html, /任务完成/)
    assert.match(html, /传输结果已知/)
    assert.match(html, /LLM 整题审查通过/)
    assert.match(html, /绑定一致/)
    assert.match(html, /未作形式化验证/)
    assert.doesNotMatch(html, /status-code[^>]*>unknown|检查通过|形式化证明通过/)
  } finally {
    await server.close()
  }
})

test('terminal SSE keeps semantics and legacy Job success in the existing store', () => {
  const semantics = {
    version: 'star-result-semantics-v1', execution: 'completed', transport: 'known',
    whole_review: 'accepted', binding: 'same_artifact', formal_verification: 'not_verified',
  }
  const raw = { id: '1', hasIdField: true, event: 'final_result', data: JSON.stringify({
    type: 'final_result', message: 'star_completed_llm_reviewed', semantics, data: { summary: 'LLM reviewed' },
  }) }
  const event = decodeSseBlock(raw)
  setActivePinia(createPinia())
  const jobs = useJobsStore()
  jobs.start('run_test', 'session_test', 'running')
  jobs.applyEvent('run_test', event)
  assert.equal(jobs.byId('run_test')?.status, 'succeeded')
  assert.equal(jobs.byId('run_test')?.error, null)
  assert.deepEqual(jobs.byId('run_test')?.events[0]?.data.semantics, semantics)
  assert.throws(() => decodeSseBlock({ ...raw, data: JSON.stringify({
    type: 'final_result', data: {}, semantics: { ...semantics, formal_verification: 'verified' },
  }) }), SseProtocolError)
})

test('report distinguishes unknown, rejection, invalid binding, required and lifecycle states', async (t) => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const { default: ReportSection } = await server.ssrLoadModule('/src/components/ReportSection.vue')
    const base = {
      version: 'star-result-semantics-v1', execution: 'needs_review', transport: 'known',
      whole_review: 'not_reviewed', binding: 'unbound', formal_verification: 'not_verified',
    }
    const cases = [
      [{ transport: 'unknown' }, '远端请求结果未知，需要人工决定'],
      [{ whole_review: 'rejected' }, 'LLM 整题审查拒绝'],
      [{ whole_review: 'invalid_source' }, '整题审查来源无效'],
      [{ whole_review: 'accepted', binding: 'artifact_changed' }, '文本已改写，旧审查不适用于当前答案'],
      [{ whole_review: 'accepted', binding: 'same_artifact', verification_requirement: 'required_unmet' }, 'required 模式的额外验证要求尚未满足'],
      [{ execution: 'running', transport: 'pending' }, '任务运行中'],
      [{ execution: 'canceled', transport: 'unknown' }, '任务已取消'],
      [{ execution: 'failed' }, '任务执行失败'],
    ] as const
    for (const [overrides, text] of cases) {
      await t.test(text, async () => {
        const report = reportSchema.parse({ version: 'report-v0.2', evidence_id: 'run_test', status: 'NEEDS_REVIEW', mode: 'star_limited', report: {
          answer: 'candidate', public_summary: '', stage: 'terminal', tool_summaries: [],
          checks: { status: 'unknown' }, limitations: [], semantics: { ...base, ...overrides },
        } })
        const html = await renderToString(createSSRApp(ReportSection, { report: report.report }))
        assert.ok(html.includes(text), html)
        assert.match(html, /未作形式化验证/)
        assert.doesNotMatch(html, /任务完成|形式化证明通过/)
      })
    }
    await t.test('legacy report still shows conservative unknown', async () => {
      const html = await renderToString(createSSRApp(ReportSection, { report: {
        answer: '<script>alert(1)</script>', public_summary: '', stage: 'terminal', limitations: [], checks: { status: 'unknown' },
      } }))
      assert.match(html, /未知/)
      assert.doesNotMatch(html, /任务完成|LLM 整题审查通过|<script>/)
    })
    await t.test('appended local checks show both historical scopes', async () => {
      const html = await renderToString(createSSRApp(ReportSection, { report: {
        answer: '1+1=2', public_summary: '', stage: 'terminal', limitations: [], checks: { status: 'unknown', history: [
          { scope: 'whole_solution_llm_review', findings: ['llm_whole_review_accept'], status: 'unknown' },
          { scope: 'polynomial_candidates', status: 'unknown' },
        ] },
      } }))
      assert.match(html, /验证历史/)
      assert.match(html, /whole_solution_llm_review/)
      assert.match(html, /polynomial_candidates/)
    })
  } finally {
    await server.close()
  }
})
