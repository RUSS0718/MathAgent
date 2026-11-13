import { expect, test } from '@playwright/test'
import { mockWorkspace, report } from './fixtures'

test('saved intervention provenance reopens read-only at desktop and mobile widths', async ({ page }, info) => {
  await mockWorkspace(page, true)
  const errors: string[] = [], mutations: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', request => {
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method())) mutations.push(request.url())
  })
  await page.route('**/api/agent/jobs/run-demo/report', route => route.fulfill({ json: {
    ...report, solver: { solver_mode: 'star_faithful', evidence_kind: 'fault_injection', missing_capabilities: [],
      solver: { run_id: 'run-demo', state_revision: 23, phase: 'STEP_EXECUTE', status: 'running',
        serial_intervention: { status: 'completed', pair_id: 'pair-demo', continuation: 'main_task_continues',
          decision: { reason: '核对缺失边界', hypothesis: '原方法未覆盖边界', method_id: 'induction' },
          adoptions: [{ status: 'adopted', reason: 'applicable_reviewed_result', evidence_grade: 'LLM_REVIEWED',
            reference: { pair_id: 'pair-demo', arm: 'intervention', source_version: 'a'.repeat(64), scope: '步骤 2' } }],
        },
      } },
  } }))
  for (const width of [320, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    await page.goto('/dashboard-assets/run/run-demo')
    const region = page.getByRole('region', { name: '串行自主干预', exact: true })
    await expect(region).toContainText('主任务继续')
    await region.getByText('成果来源与采用记录', { exact: true }).click()
    await expect(region).toContainText('已采用')
    await expect(region).toContainText('LLM_REVIEWED')
    await expect(region).toContainText('来源 pair-demo')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.reload()
  await expect(page.getByRole('region', { name: '串行自主干预', exact: true })).toContainText('整题审查')
  await page.screenshot({ path: info.outputPath('intervention-reopened.png'), fullPage: true })
  expect(errors).toEqual([])
  expect(mutations).toEqual([])
})
