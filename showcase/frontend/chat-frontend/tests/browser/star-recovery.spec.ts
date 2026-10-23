import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mockWorkspace, report } from './fixtures'

for (const width of [320, 1440]) {
  test(`unknown call requires explicit fresh identity at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 })
    const problems: string[] = []
    page.on('pageerror', error => problems.push(error.message))
    await mockWorkspace(page, false, 'id: 1\nevent: needs_review\ndata: {"type":"needs_review","status":"failed"}\n\n')
    await page.route('**/api/agent/jobs/run-demo', route => route.fulfill({ json: {
      success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'failed', error: 'star_needs_review',
    } }))
    await page.route('**/api/agent/jobs/run-demo/report', route => route.fulfill({ json: {
      ...report, mode: 'star_limited', status: 'NEEDS_REVIEW',
      report: { ...report.report, budget: { http_attempts: 1, unknown_attempts: 1, reserved_tokens: 512, charged_tokens: 512, deadline_at: 1792770000 } },
      solver: { solver_mode: 'star_limited', evidence_kind: 'fault_injection', missing_capabilities: [],
        solver: { run_id: 'run-demo', state_revision: 5, phase: 'EXPLORE', status: 'interrupted',
          recovery: { status: 'needs_review', unknown_calls: [{ call_id: 'unknown-call', role: 'explore', status: 'unknown_outcome' }], retries: [] } } },
    } }))
    const decisions: Record<string, unknown>[] = []
    await page.route('**/api/agent/jobs/run-demo/resume', async route => {
      decisions.push(route.request().postDataJSON())
      await route.fulfill({ json: { success: true, job_id: 'run-demo', status: 'queued' } })
    })
    await page.goto('/dashboard-assets/run/run-demo')
    const action = page.getByRole('button', { name: '明确选择：用新身份重试' })
    await expect(action).toBeVisible()
    await expect(page.getByText('选择重试会产生新的调用身份', { exact: false })).toBeVisible()
    expect(decisions).toHaveLength(0)
    await page.getByRole('button', { name: '重连事件（沿用游标）' }).click()
    await expect(action).toBeVisible()
    expect(decisions).toHaveLength(0)
    await action.click()
    await expect.poll(() => decisions.length).toBe(1)
    const retry = decisions[0].retry_call as { call_id: string; new_call_id: string }
    expect(retry.call_id).toBe('unknown-call')
    expect(retry.new_call_id).toMatch(/^[0-9a-f-]{36}$/)
    expect(retry.new_call_id).not.toBe(retry.call_id)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
    expect(problems).toEqual([])
    await page.screenshot({ path: testInfo.outputPath(`unknown-retry-${width}.png`), fullPage: true })
  })
}
