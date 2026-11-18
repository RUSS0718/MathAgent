import { expect, test } from '@playwright/test'
import { mockWorkspace, report } from './fixtures'

test('opt-in memory review shows the persisted evidence level and advisory history', async ({ page }) => {
  await mockWorkspace(page)
  await page.route('**/api/sessions/session-demo/goal-cache', route =>
    route.fulfill({ status: 404, json: { code: 'not_found' } }))
  await page.route('**/api/sessions/session-demo/memory/**', route =>
    route.fulfill({ status: 404, json: { code: 'not_found' } }))
  await page.route('**/api/agent/jobs/run-demo/memory', route => route.fulfill({ json: {
    success: true,
    run_memory: {
      run_id: 'run-demo', source: 'authoritative_run_snapshot', state_revision: 4,
      phase: 'TERMINAL', status: 'completed', plan_version: 2, graph_version: 3,
      budget: { http_attempts: 1 }, invalidated_count: 0,
      valid_evidence: [{ result_id: 'evidence-1', evidence_level: 'llm_reviewed', category: 'Lemma' }],
    },
  } }))
  await page.route('**/api/sessions/session-demo/population-memory', route => route.fulfill({ json: {
    success: true, authority: 'observations_only', total_jobs: 1, limit: 25, offset: 0,
    observations: [{ source_run_id: 'run-older', source_state_revision: 2,
      route_id: 'route-1', parent_route_id: null, status: 'stopped', stop_reason: null,
      graph_version: 1, plan_version: 1, policy_version: 1, unknown_observation_count: 1 }],
  } }))

  await page.goto('/dashboard-assets/run/run-demo')
  const memory = page.getByRole('region', { name: '运行记忆与历史路线观察' })
  await expect(memory).toBeVisible()
  await expect(memory).toContainText('authoritative_run_snapshot')
  await expect(memory).toContainText('evidence-1 · 等级：llm_reviewed · 类别：Lemma')
  await expect(memory).toContainText('run-older')
  await expect(memory).toContainText('未知观察数')
  await expect(memory).toContainText('不构成数学证明')
  await page.setViewportSize({ width: 390, height: 844 })
  const widths = await memory.evaluate(element => ({
    panel: element.getBoundingClientRect().width,
    content: element.scrollWidth,
    viewport: window.innerWidth,
  }))
  expect(widths.panel).toBeLessThanOrEqual(widths.viewport)
  expect(widths.content).toBeLessThanOrEqual(widths.panel + 1)
})

test('default-off memory routes leave the review panel hidden', async ({ page }) => {
  await mockWorkspace(page)
  await page.route('**/api/sessions/session-demo/goal-cache', route =>
    route.fulfill({ status: 404, json: { code: 'not_found' } }))
  await page.route('**/api/sessions/session-demo/memory/**', route =>
    route.fulfill({ status: 404, json: { code: 'not_found' } }))
  await page.goto('/dashboard-assets/run/run-demo')
  await expect(page.getByRole('region', { name: '运行记忆与历史路线观察' })).toHaveCount(0)
})

test('serial route review shows advisory provenance and separate estimated injection cost', async ({ page }) => {
  await mockWorkspace(page)
  await page.route('**/api/sessions/session-demo/goal-cache', route =>
    route.fulfill({ status: 404, json: { code: 'not_found' } }))
  await page.route('**/api/sessions/session-demo/memory/**', route =>
    route.fulfill({ status: 404, json: { code: 'not_found' } }))
  await page.route('**/api/agent/jobs/run-demo/report', route => route.fulfill({ json: {
    ...report,
    mode: 'star_limited',
    solver: {
      solver_mode: 'star_limited', evidence_kind: 'fault_injection', missing_capabilities: [],
      solver: {
        run_id: 'run-demo', state_revision: 9, phase: 'TERMINAL', status: 'completed_llm_reviewed',
        progress: { routes: {
          policy_version: 'serial-aprs-v1', active_route_id: 'route-current', items: [{
            route_id: 'route-current', parent_route_id: null, kind: 'primary', status: 'completed',
            frontier_digest: 'frontier-current', graph_version: 3, policy_version: 'serial-aprs-v1',
          }],
          decisions: [],
          evaluations: [{
            route_id: 'route-current', input_hash: 'a'.repeat(64), hard_gate: true, current: true,
            memory_hits: [{ record_id: 'memory-hit', source_run_id: 'source-run', outcome: 'success',
              use: 'candidate_guidance', review_status: 'requires_current_run_review',
              authority: 'advisory_only', imported_from: { record_id: 'original-memory' } }],
            population_memory_cost: { status: 'estimated', call_count: 2, estimated_tokens: 42,
              additional_utf8_bytes: 126, estimator_versions: ['utf8-byte-ceil-third-v1-estimated'] },
            vector: { verified_gain: 0, evidence_quality: 0, novelty: 0, cost: 13,
              cost_known: true, http_attempts: 2, tool_calls: 0, wall_time_seconds: 1,
              unknown_attempts: 0 },
          }, {
            route_id: 'route-unknown', input_hash: 'b'.repeat(64), hard_gate: false, current: false,
            memory_hits: [{ record_id: 'unknown-cost-memory', source_run_id: 'source-run',
              outcome: 'unknown', review_status: 'requires_current_run_review', authority: 'advisory_only' }],
            population_memory_cost: { status: 'unknown', call_count: 0, estimated_tokens: null,
              additional_utf8_bytes: null, estimator_versions: [] },
            vector: { verified_gain: 0, evidence_quality: 0, novelty: 0, cost: null,
              cost_known: false, http_attempts: null, tool_calls: null, wall_time_seconds: null,
              unknown_attempts: 1 },
          }],
        } },
      },
    },
  } }))

  await page.goto('/dashboard-assets/run/run-demo')
  const routes = page.getByRole('region', { name: '串行路线与裁决' })
  await expect(routes).toContainText('记录 memory-hit')
  await expect(routes).toContainText('source-run')
  await expect(routes).toContainText('original-memory')
  await expect(routes).toContainText('仅 advisory')
  await expect(routes).toContainText('requires_current_run_review')
  await expect(routes).toContainText('42')
  await expect(routes).toContainText('126')
  await expect(routes).toContainText('成本未知；没有归属完整的估算，不按零成本处理')
  await expect(routes).not.toContainText('historical private content')
  await page.setViewportSize({ width: 390, height: 844 })
  const widths = await routes.evaluate(element => ({
    panel: element.getBoundingClientRect().width,
    content: element.scrollWidth,
    viewport: window.innerWidth,
  }))
  expect(widths.panel).toBeLessThanOrEqual(widths.viewport)
  expect(widths.content).toBeLessThanOrEqual(widths.panel + 1)
})
