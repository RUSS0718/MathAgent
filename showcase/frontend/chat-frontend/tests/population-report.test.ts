import test from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { reportSchema } from '../src/api/reports.schemas.ts'

test('Population report exposes mathematical delivery separately from request settlement', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const { default: StarRunReview } = await server.ssrLoadModule('/src/components/StarRunReview.vue')
    const { default: StarModeSelector } = await server.ssrLoadModule('/src/components/StarModeSelector.vue')
    const report = reportSchema.parse({
      version: 'report-v0.2', evidence_id: 'run_population', status: 'COMPLETED', mode: 'star_population',
      solver: {
        solver_mode: 'star_population', evidence_kind: 'fault_injection', missing_capabilities: [],
        solver: {
          run_id: 'run_population', state_revision: 8, phase: 'TERMINAL', status: 'completed',
          execution_selection: {
            selected: 'population', reason: 'independent_routes_admitted',
            proposal_reason: '独立的代数与构造方向', independent_routes: 2,
            capacity: { max_inflight: 2, worker_slots: 2 },
            budget: { logical_calls: 3, deadline_at: 9999999999,
              limits: { max_model_calls: 48, max_tokens: 2097152 } },
          },
          population: {
            version: 'population-v1',
            routes: [{ ordinal: 1, parent_ordinal: null, status: 'completed',
              step_count: 2, completed_steps: 2, result: 'accepted_evidence' },
            { ordinal: 2, parent_ordinal: 1, status: 'unknown',
              step_count: 3, completed_steps: 1, result: 'pending' }],
            scheduler: {
              round: 2, member_count: 2, opportunities_used: 2,
              verified_gain_count: 1, route_counts: { completed: 1, unknown: 1 }, paused: false,
            },
            resources: { worker_slots_in_use: 0, http_inflight: 1, unknown_routes: 1, unknown_requests: 1 },
            delivery: { status: 'delivered', reason: 'final_answer_bound' },
            settlement: { status: 'pending', unknown_count: 1 },
          },
        },
      },
      report: {
        answer: '1+1=2', public_summary: '受控回复', stage: 'terminal', tool_summaries: [],
        checks: { status: 'unknown', history: [] }, limitations: [],
      },
    })
    const html = await renderToString(createSSRApp(StarRunReview, { report, jobId: 'run_population' }))
    assert.match(html, /并发路线执行/)
    assert.match(html, /自主路线选择/)
    assert.match(html, /实际求解路线/)
    assert.match(html, /独立的代数与构造方向/)
    assert.match(html, /已接受步骤 2 \/ 2/)
    assert.match(html, /已接受步骤 1 \/ 3/)
    assert.match(html, /选择时已用模型调用 3 \/ 48/)
    assert.match(html, /数学交付/)
    assert.match(html, /请求结算/)
    assert.match(html, /已交付/)
    assert.match(html, /结算中/)
    assert.match(html, /未知请求.*1/)
    assert.doesNotMatch(html, /frontier_digest|population_action_id|route-SECRET/)
    const selector = await renderToString(createSSRApp(StarModeSelector, {
      modelValue: 'star_population',
      modes: [{ solver_mode: 'star_population', enabled: true }],
      disabled: false,
    }))
    assert.match(selector, /STAR 并发 Population\/APRS/)
  } finally {
    await server.close()
  }
})
