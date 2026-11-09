import { expect, test, type Page } from '@playwright/test'
import { mockWorkspace } from './fixtures'

const runId = 'run-demo'
const privatePrompt = 'fixture-private-prompt-not-for-display'
const privateToken = 'fixture-token-not-for-display'

/** Controlled public API data; this fixture does not contact a provider. */
const populationReport = {
  version: '1',
  evidence_id: 'population-fixture-evidence',
  mode: 'star_population',
  status: 'succeeded',
  report: {
    budget: { http_attempts: 2, unknown_attempts: 1, reserved_tokens: 512, charged_tokens: 128 },
    answer: '受控浏览器夹具答案。',
    request_attempts: [{
      attempt_id: 'fixture-attempt-1', status: 'completed', requested_model: 'controlled-fixture',
      usage: { total_tokens: 128 }, private_token: privateToken,
    }],
    public_summary: '受控 API 夹具，仅验证报告投影。',
    stage: 'terminal',
    tool_summaries: [],
    checks: { status: 'unknown', findings: [] },
    limitations: ['不代表真实 provider 行为或数学效果。'],
  },
  solver: {
    solver_mode: 'star_population',
    evidence_kind: 'controlled_fixture',
    missing_capabilities: [],
    solver: {
      run_id: runId,
      state_revision: 42,
      phase: 'TERMINAL',
      status: 'completed',
      private_prompt: privatePrompt,
      population: {
        version: 'population-v1',
        scheduler: {
          round: 3,
          member_count: 2,
          opportunities_used: 4,
          verified_gain_count: 1,
          route_counts: { completed: 2 },
          paused: true,
        },
        resources: {
          worker_slots_in_use: 0,
          http_inflight: 0,
          unknown_routes: 0,
          unknown_requests: 1,
        },
        delivery: { status: 'delivered', reason: 'independent_review_passed' },
        settlement: { status: 'pending', unknown_count: 1 },
        private_payload: privatePrompt,
      },
    },
  },
}

/** Serves deterministic Job, report, and terminal SSE responses. */
async function installPopulationFixture(page: Page): Promise<{
  eventReads: () => number
  reportReads: () => number
  postPaths: string[]
}> {
  let events = 0
  let reports = 0
  const postPaths: string[] = []
  await mockWorkspace(page, false, 'id: 2\nevent: final_result\ndata: {"type":"final_result","status":"succeeded","data":{}}\n\n')
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (url.pathname.startsWith('/api/') && request.method() === 'POST') postPaths.push(url.pathname)
    if (url.pathname === `/api/agent/jobs/${runId}/events`) events += 1
  })
  await page.route(`**/api/agent/jobs/${runId}/report`, async (route) => {
    reports += 1
    await route.fulfill({ json: populationReport })
  })
  return { eventReads: () => events, reportReads: () => reports, postPaths }
}

for (const viewport of [
  { name: 'desktop', width: 1440, height: 1000 },
  { name: 'mobile', width: 375, height: 812 },
]) {
  test(`Population report persists with separate delivery and settlement on ${viewport.name}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    const fixture = await installPopulationFixture(page)

    await page.goto(`/dashboard-assets/run/${runId}`)

    const population = page.getByRole('region', { name: '并发路线执行' })
    await expect(population).toBeVisible()
    await expect(population.locator('dt').filter({ hasText: '调度轮次' }).locator('xpath=following-sibling::dd[1]')).toHaveText('3')
    await expect(population.locator('dt').filter({ hasText: '数学交付' }).locator('xpath=following-sibling::dd[1]')).toContainText('已交付')
    await expect(population.locator('dt').filter({ hasText: '请求结算' }).locator('xpath=following-sibling::dd[1]')).toContainText('结算中')
    await expect(population.locator('dt').filter({ hasText: '请求结算' }).locator('xpath=following-sibling::dd[1]')).toContainText('未知请求 1')
    await expect(page.getByText(String(populationReport.solver.solver.state_revision), { exact: true })).toBeVisible()
    await expect.poll(fixture.eventReads).toBeGreaterThan(0)
    await expect.poll(fixture.reportReads).toBeGreaterThan(0)

    const refresh = page.getByRole('button', { name: '刷新持久报告' })
    const reconnect = page.getByRole('button', { name: '重连事件（沿用游标）' })
    await expect(refresh).toBeEnabled()
    await expect(reconnect).toBeEnabled()

    const reportsBeforeRefresh = fixture.reportReads()
    await refresh.click()
    await expect.poll(fixture.reportReads).toBeGreaterThan(reportsBeforeRefresh)
    await expect(population.locator('dt').filter({ hasText: '数学交付' }).locator('xpath=following-sibling::dd[1]')).toContainText('已交付')
    expect(fixture.postPaths).toEqual([])

    const eventsBeforeReconnect = fixture.eventReads()
    const reportsBeforeReconnect = fixture.reportReads()
    await reconnect.click()
    await expect.poll(fixture.eventReads).toBeGreaterThan(eventsBeforeReconnect)
    await expect.poll(fixture.reportReads).toBeGreaterThan(reportsBeforeReconnect)
    await expect(population.locator('dt').filter({ hasText: '请求结算' }).locator('xpath=following-sibling::dd[1]')).toContainText('结算中')
    expect(fixture.postPaths).toEqual([])

    const reportsBeforeReload = fixture.reportReads()
    await page.reload()
    await expect(page.getByRole('region', { name: '并发路线执行' })).toBeVisible()
    await expect.poll(fixture.reportReads).toBeGreaterThan(reportsBeforeReload)
    await expect(page.getByRole('region', { name: '并发路线执行' }).locator('dt').filter({ hasText: '数学交付' }).locator('xpath=following-sibling::dd[1]')).toContainText('已交付')
    await expect(page.getByRole('region', { name: '并发路线执行' }).locator('dt').filter({ hasText: '请求结算' }).locator('xpath=following-sibling::dd[1]')).toContainText('结算中')
    await expect(page.getByText(String(populationReport.solver.solver.state_revision), { exact: true })).toBeVisible()
    expect(fixture.postPaths).toEqual([])

    const pageText = await page.locator('body').textContent()
    expect(pageText).not.toContain(privatePrompt)
    expect(pageText).not.toContain(privateToken)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath(`population-report-${viewport.name}.png`), fullPage: true })
  })
}
