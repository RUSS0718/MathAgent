import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mockWorkspace, report } from './fixtures'

// Presentation evidence only; actual STAR dispatch is tested through Python HTTP contracts.
for (const width of [320, 768, 1024, 1440]) {
  test(`explicit limited STAR selector and honest identity at ${width}px`, async ({ page }, testInfo) => {
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('console', (message) => { if (['error', 'warning'].includes(message.type())) errors.push(message.text()) })
    await page.setViewportSize({ width, height: 1000 })
    await mockWorkspace(page)
    await page.route('**/api/capabilities', (route) => route.fulfill({ json: {
      profile: 'showcase', execution: { mode: 'fake', provider: 'demo', status: 'configured' },
      jobs: { enabled: true, status: 'available' }, sse: { enabled: true, status: 'available' },
      verification_mode: ['auto'], files: { upload: { enabled: false } },
      capabilities: { jobs: true, sse: true, verification_mode: ['auto'], file_upload: { enabled: false } },
      solver_modes: [{ solver_mode: 'star_limited', enabled: true, missing_capabilities: ['isolated_python_output_guard'] }],
    } }))
    await page.route('**/api/agent/jobs/*/report', (route) => route.fulfill({ json: {
      ...report, mode: 'star_limited', report: { ...report.report, checks: { status: 'unknown', findings: ['LLM 整题审查不等于形式化证明'] }, public_summary: '受控传输展示：探索、润色和整题审查已执行；不代表数学能力验收。' }, solver: { solver_mode: 'star_limited', evidence_kind: 'scripted',
        missing_capabilities: ['isolated_python_output_guard', 'accepted_step_checkpoint_recovery'],
        solver: { run_id: 'run-demo', state_revision: 16, phase: 'TERMINAL', status: 'completed_llm_reviewed' } },
    } }))
    let selectedMode = ''
    await page.route('**/api/agent/jobs', async (route) => {
      selectedMode = route.request().postDataJSON().solver_mode
      await route.fulfill({ json: { success: true, job_id: 'run-demo', status: 'succeeded' } })
    })
    await page.goto('/dashboard-assets/session/session-demo')
    const selector = page.getByLabel('求解模式')
    await expect(selector).toHaveValue('legacy')
    await selector.selectOption('star_limited')
    await expect(page.getByText('探索 → 润色 → 新整题审查；隔离 Python、安全续算与完整机制尚未验收。')).toBeVisible()
    await expect(selector.locator('option', { hasText: 'STAR 完整参考' })).toBeDisabled()
    await page.getByLabel('数学问题', { exact: true }).fill('1+1')
    await page.getByRole('button', { name: '发送' }).click()
    await expect.poll(() => selectedMode).toBe('star_limited')
    await expect(page.locator('.workspace-topbar')).toContainText('STAR 受限')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
    expect(errors).toEqual([])
    await page.screenshot({ path: testInfo.outputPath(`star-limited-${width}.png`), fullPage: true })
  })
}
