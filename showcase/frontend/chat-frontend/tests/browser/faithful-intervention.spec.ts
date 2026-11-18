import { expect, test } from '@playwright/test'
import { mockWorkspace } from './fixtures'

const initialView = () => ({
  job_id: 'run-demo', status: 'paused', checkpoint_revision: 12,
  failure_sources: [{ source_event_id: 'solver_event_demo', source_state_revision: 9,
    event_type: 'step_reviewed', verdict: 'CHALLENGE', step_label: '步骤 1' }],
  root_obligations: [{ obligation_id: 'root-1', proposition: 'x = 2' }],
  current_method_id: 'direct', hypotheses: [], actions: [], pairs: [], effects: [],
})

test('pause request refreshes until the safe checkpoint is persisted', async ({ page }) => {
  await mockWorkspace(page, false, 'event: heartbeat\ndata: {"type":"heartbeat","job_id":"run-demo"}\n\n')
  await page.route('**/api/sessions/session-demo/goal-cache', route =>
    route.fulfill({ status: 404, json: { code: 'not_found' } }))
  await page.route('**/api/sessions/session-demo/memory/**', route =>
    route.fulfill({ status: 404, json: { code: 'not_found' } }))
  await page.route('**/api/agent/jobs/run-demo', route => route.fulfill({ json: {
    success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'running', last_event_id: 0,
  } }))
  const data = { ...initialView(), status: 'unpaused' }
  let pauseReads = 0
  await page.route('**/api/agent/jobs/run-demo/interventions', async route => {
    if (route.request().method() !== 'GET') return route.fulfill({ status: 405 })
    if (data.status === 'pause_requested' && ++pauseReads >= 2) data.status = 'paused'
    return route.fulfill({ json: { success: true, interventions: data } })
  })
  await page.route('**/api/agent/jobs/run-demo/interventions/pause', async route => {
    data.status = 'pause_requested'
    return route.fulfill({ status: 202, json: { success: true, job_id: 'run-demo', status: data.status } })
  })

  await page.goto('/dashboard-assets/run/run-demo')
  const panel = page.getByRole('region', { name: '同源干预实验' })
  await expect(panel).toContainText('unpaused')
  await panel.getByRole('button', { name: '请求安全暂停' }).click()
  await expect(panel).toContainText('paused', { timeout: 5000 })
  await expect(panel).toContainText('安全 checkpoint 修订')
})

test('disabled F4 routes leave no intervention controls in Run Review', async ({ page }) => {
  await mockWorkspace(page)
  await page.route('**/api/sessions/session-demo/goal-cache', route =>
    route.fulfill({ status: 404, json: { code: 'not_found' } }))
  await page.route('**/api/sessions/session-demo/memory/**', route =>
    route.fulfill({ status: 404, json: { code: 'not_found' } }))
  await page.route('**/api/agent/jobs/run-demo/interventions', route =>
    route.fulfill({ status: 404, json: { code: 'not_found' } }))
  await page.goto('/dashboard-assets/run/run-demo')
  await expect(page.getByRole('region', { name: '同源干预实验' })).toHaveCount(0)
})

test('paused parent exposes safe setup, persisted pair actions, and a narrow mobile layout', async ({ page }) => {
  await mockWorkspace(page, false, 'event: heartbeat\ndata: {"type":"heartbeat","job_id":"run-demo"}\n\n')
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.route('**/api/sessions/session-demo/goal-cache', route =>
    route.fulfill({ status: 404, json: { code: 'not_found' } }))
  await page.route('**/api/sessions/session-demo/memory/**', route =>
    route.fulfill({ status: 404, json: { code: 'not_found' } }))
  let data = initialView()
  await page.route('**/api/agent/jobs/run-demo', route => route.fulfill({
    json: { success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'waiting_input', last_event_id: 0 },
  }))
  await page.route('**/api/agent/jobs/run-demo/interventions', async route => {
    if (route.request().method() === 'GET') return route.fulfill({ json: { success: true, interventions: data } })
    return route.fulfill({ status: 405 })
  })
  let pairId = ''
  await page.route('**/api/agent/jobs/run-demo/interventions/**', async route => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()
    if (path.endsWith('/actions') && method === 'POST') {
      const action = route.request().postDataJSON() as { action_id: string; action_type: string; parameters: { method_id: string } }
      data.actions = [...data.actions, { action_id: action.action_id, action_type: action.action_type,
        target: 'current_step', parameters: action.parameters }]
      return route.fulfill({ json: { success: true, action_id: action.action_id } })
    }
    if (path.endsWith('/hypotheses') && method === 'POST') {
      const hypothesis = route.request().postDataJSON() as { hypothesis_id: string; failure_category: string }
      data.hypotheses = [...data.hypotheses, { hypothesis_id: hypothesis.hypothesis_id,
        failure_category: hypothesis.failure_category, status: 'active' }]
      return route.fulfill({ json: { success: true, hypothesis_id: hypothesis.hypothesis_id,
        source_event_id: 'solver_event_demo', source_state_revision: 9 } })
    }
    if (path.endsWith('/pairs') && method === 'POST') {
      const pair = route.request().postDataJSON() as { pair_id: string; control_action_id: string; intervention_action_id: string }
      pairId = pair.pair_id
      data.pairs = [...data.pairs, { pair_id: pair.pair_id, status: 'reserved', denominator: 0,
        evaluable_pairs: 0, effect: null, budget_reservation: { logical_calls: 4, http_attempts: 4 },
        arms: { control: { action_id: pair.control_action_id, status: 'not_started' },
          intervention: { action_id: pair.intervention_action_id, status: 'not_started' } } }]
      return route.fulfill({ json: { success: true, pair_id: pair.pair_id, status: 'reserved' } })
    }
    if (pairId && path.endsWith(`/${pairId}/execute`) && method === 'POST') {
      data.pairs = data.pairs.map(pair => pair.pair_id === pairId ? { ...pair, status: 'running' } : pair)
      return route.fulfill({ status: 202, json: { success: true, pair_id: pairId, status: 'scheduled' } })
    }
    if (path.endsWith('/resume') && method === 'POST') {
      data.status = 'resuming'
      return route.fulfill({ status: 202, json: { success: true, job_id: 'run-demo', status: 'running' } })
    }
    return route.fulfill({ status: 404, json: { code: 'not_found' } })
  })

  await page.goto('/dashboard-assets/run/run-demo')
  const panel = page.getByRole('region', { name: '同源干预实验' })
  await expect(panel).toBeVisible()
  await expect(panel).toContainText('控制状态')
  await expect(panel).toContainText('继承当前暂停 checkpoint')
  await panel.getByRole('button', { name: '登记并预留' }).click()
  await expect.poll(() => pairId).not.toBe('')
  await expect(panel).toContainText(`配对 ${pairId}`)
  await expect(panel).toContainText('http_attempts')
  await panel.getByRole('button', { name: '显式启动这组分支' }).click()
  await expect(panel).toContainText('配对执行已排队')
  await expect(panel).toContainText('控制臂')
  await expect(panel).toContainText('未知（未提供）')
  await expect(panel.getByRole('button', { name: '显式恢复父 Run' })).toHaveCount(0)
  data.pairs = data.pairs.map(pair => pair.pair_id === pairId ? {
    ...pair,
    status: 'completed',
    arms: {
      control: { action_id: 'control', status: 'completed', branch_verifier_verdict: 'ACCEPT', independent_recheck_verdict: 'ACCEPT', evidence_integrity: 'verified' },
      intervention: { action_id: 'variant', status: 'completed', branch_verifier_verdict: 'ACCEPT', independent_recheck_verdict: 'ACCEPT', evidence_integrity: 'verified' },
    },
  } : pair)
  await panel.getByRole('button', { name: '刷新干预状态' }).click()
  await expect(panel).toContainText('分支执行时 Verifier 裁决：ACCEPT')
  await expect(panel).toContainText('持久子状态一致性检查：verified')
  await panel.getByRole('button', { name: '显式恢复父 Run' }).click()
  await expect(panel).toContainText('已请求在原 Run 中显式续算')

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(panel).toBeVisible()
  const widths = await panel.evaluate(element => ({
    panel: element.getBoundingClientRect().width,
    content: element.scrollWidth,
    viewport: window.innerWidth,
  }))
  expect(widths.panel).toBeLessThanOrEqual(widths.viewport)
  expect(widths.content).toBeLessThanOrEqual(widths.panel + 1)
})
