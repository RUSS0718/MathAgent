import { expect, test } from '@playwright/test'
import { mockWorkspace, report } from './fixtures'

test('saved switch states survive read-only report reopening on desktop and mobile', async ({ page }, testInfo) => {
  await mockWorkspace(page, true)
  let status = 'converging'
  const errors: string[] = []
  const mutations: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', request => {
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method())) mutations.push(request.url())
  })
  await page.route('**/api/agent/jobs/run-demo/report', route => route.fulfill({ json: {
    ...report, solver: { solver_mode: 'star_faithful', evidence_kind: 'fault_injection', missing_capabilities: [],
      solver: { run_id: 'run-demo', state_revision: 17, phase: 'STEP_EXECUTE', status: 'running',
        execution_switch: { status, source: 'population', target: 'serial', reason: '独立方向已收敛', checkpoint_revision: 17 },
      } },
  } }))
  for (const [value, label] of [['converging', '切换中'], ['needs_review', '待复核'], ['switched', '已切换']]) {
    status = value!
    await page.goto('/dashboard-assets/run/run-demo')
    const region = page.getByRole('region', { name: '运行路线切换' })
    await expect(region).toContainText(label!)
    await expect(region).toContainText('并发 → 串行')
  }
  await page.setViewportSize({ width: 375, height: 850 })
  await page.reload()
  await expect(page.getByRole('region', { name: '运行路线切换' })).toContainText('检查点版本 17')
  await page.screenshot({ path: testInfo.outputPath('switch-mobile.png'), fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(errors).toEqual([])
  expect(mutations).toEqual([])
})
