import test from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { formalVerificationSchema, reportSchema } from '../src/api/reports.schemas.ts'
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

test('formal verification stays separate from the original answer and legacy review', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  const record = {
    schema_version: 'formal-verification-v1',
    policy: {
      enabled: true, backend: 'lean_tactic_prover', timeout_seconds: 30,
      environment: {
        lean_version: '4.19.0', mathlib_version: 'v4.19.0',
        toolchain: 'leanprover/lean4:v4.19.0', image_digest: 'sha256:' + 'b'.repeat(64),
        manifest_digest: 'c'.repeat(64), template_version: 'rational-polynomial-v1',
      },
      target: { lhs: 'x + x', rhs: '2 * x', private_prompt: 'HIDDEN_FORMAL_PROMPT' },
      api_token: 'HIDDEN_FORMAL_TOKEN',
    },
    policy_hash: 'a'.repeat(64),
    status: 'unavailable', grade: null,
    current_attempt_id: 'formal_attempt_1',
    current: {
      schema_version: 1, status: 'unavailable', grade: null,
      attempt_id: 'formal_attempt_1', parent_attempt_id: null,
      reason: 'lean_runtime_unavailable',
      proof_artifact: null,
      specifications: {
        original_to_spec: {
          original_problem_hash: 'd'.repeat(64), problem_spec_hash: 'e'.repeat(64),
          root_obligations: [{ obligation_id: 'root:identity', statement: 'x + x = 2 * x' }],
          review_status: 'not_reviewed', review_record_hash: null,
        },
        spec_to_target: { review_status: 'not_reviewed', review_record_hash: null },
        target_to_environment: { review_status: 'not_reviewed', review_record_hash: null },
      },
      cost: { elapsed_seconds: 0.1, output_bytes: 0, unknown: false },
      lineage: { attempt_id: 'formal_attempt_1', parent_attempt_id: null, sequence: 1 },
    },
    attempts: [],
    lineage: {
      parent_attempt_id: null, attempt_ids: ['formal_attempt_1'],
      total_cost: { elapsed_seconds: 0.1, output_bytes: 0 },
    },
  }
  record.attempts = [record.current]
  assert.equal(formalVerificationSchema.parse(record).status, 'unavailable')
  try {
    const { default: FormalVerificationSection } = await server.ssrLoadModule('/src/components/FormalVerificationSection.vue')
    const html = await renderToString(createSSRApp(FormalVerificationSection, { verification: record }))
    assert.match(html, /形式验证/)
    assert.match(html, /不可用/)
    assert.match(html, /原答案仍保留/)
    assert.match(html, /lean_tactic_prover/)
    assert.match(html, /formal_attempt_1/)
    assert.match(html, /4\.19\.0/)
    assert.match(html, /0\.1/)
    assert.doesNotMatch(html, /HIDDEN_FORMAL_PROMPT|HIDDEN_FORMAL_TOKEN/)
  } finally {
    await server.close()
  }
})

test('only backend solved grades render as L2 or L3 and correspondence stays independent', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const { default: FormalVerificationSection } = await server.ssrLoadModule('/src/components/FormalVerificationSection.vue')
    const base = {
      schema_version: 'formal-verification-v1',
      policy: { enabled: true, backend: 'lean_tactic_prover', timeout_seconds: 30, environment: { lean_version: '4.19.0' } },
      policy_hash: 'a'.repeat(64), current_attempt_id: 'formal_2',
      current: {
        schema_version: 1, status: 'solved', grade: 'L2', attempt_id: 'formal_2', parent_attempt_id: 'formal_1',
        reason: null, proof_artifact: { source_hash: '1'.repeat(64), proof_hash: '2'.repeat(64), cleanup_verified: true, axioms: ['propext'] },
        specifications: { original_to_spec: { review_status: 'not_reviewed', review_record_hash: null } },
        cost: { elapsed_seconds: 2.5, output_bytes: 240 }, lineage: { attempt_id: 'formal_2', parent_attempt_id: 'formal_1', sequence: 2 },
      },
      attempts: [
        { schema_version: 1, status: 'timeout', grade: null, attempt_id: 'formal_1', parent_attempt_id: null, reason: 'deadline', cost: { elapsed_seconds: 30, output_bytes: 0, unknown: true } },
      ],
      lineage: { parent_attempt_id: 'formal_1', attempt_ids: ['formal_1', 'formal_2'], total_cost: { elapsed_seconds: 32.5, output_bytes: 240 } },
    }
    const l2 = await renderToString(createSSRApp(FormalVerificationSection, { verification: { ...base, status: 'solved', grade: 'L2' } }))
    assert.match(l2, /形式目标已核验/)
    assert.match(l2, /原题对应待独立复核/)
    assert.match(l2, /formal_1/)
    assert.match(l2, /32\.5/)

    const forged = { ...base, status: 'solved', grade: 'L2', current: { ...base.current, grade: 'L2' } }
    const l2Only = await renderToString(createSSRApp(FormalVerificationSection, { verification: forged }))
    assert.match(l2Only, /原题对应待独立复核/)
    assert.doesNotMatch(l2Only, /形式目标与规格对应已独立核验/)

    const dispatched = await renderToString(createSSRApp(FormalVerificationSection, { verification: { ...base, status: 'dispatched', grade: null, current: { ...base.current, status: 'dispatched', grade: null } } }))
    assert.match(dispatched, /形式化验证进行中，尚未确认/)
    assert.doesNotMatch(dispatched, /status-badge[^>]*>L2|status-badge[^>]*>L3|形式目标已核验|形式目标与规格对应已独立核验/)

    const solvedWithoutGrade = await renderToString(createSSRApp(FormalVerificationSection, {
      verification: { ...base, status: 'solved', grade: null, current: { ...base.current, status: 'solved', grade: null } },
    }))
    assert.match(solvedWithoutGrade, /没有可公开的 L2\/L3 等级/)
    assert.doesNotMatch(solvedWithoutGrade, /内核已接受/)
    assert.doesNotMatch(solvedWithoutGrade, /status-badge[^>]*>L2|status-badge[^>]*>L3/)

    const l3 = await renderToString(createSSRApp(FormalVerificationSection, { verification: {
      ...base, status: 'solved', grade: 'L3', current: { ...base.current, grade: 'L3', specifications: {
        original_to_spec: { review_status: 'reviewed', review_record_hash: '3'.repeat(64) },
        spec_to_target: { review_status: 'reviewed', review_record_hash: '4'.repeat(64) },
        target_to_environment: { review_status: 'reviewed', review_record_hash: '5'.repeat(64) },
      } },
    } }))
    assert.match(l3, /形式目标与规格对应已独立核验/)
  } finally {
    await server.close()
  }
})
