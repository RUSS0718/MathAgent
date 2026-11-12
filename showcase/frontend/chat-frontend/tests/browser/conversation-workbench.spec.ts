import { expect, test } from '@playwright/test'
import { mockWorkspace, report } from './fixtures'

function frame(id: number, type: string, extra: Record<string, unknown>) {
  return `id: ${id}\nevent: ${type}\ndata: ${JSON.stringify({ type, ...extra })}\n\n`
}

test('default page replaces old chat and submits the actual entered problem with CSRF', async ({ page }) => {
  await mockWorkspace(page, false, stream)
  let submitted = false
  let creations = 0
  await page.route('**/api/load_session?*', route => route.fulfill({ json: { success: true,
    messages: submitted ? [{ sender: 'user', text: '求解 x+1=2', analysis_job_id: 'run-demo' }] : [] } }))
  await page.route('**/api/agent/jobs', async route => {
    creations += 1
    expect(route.request().headers()['x-csrf-token']).toBe('synthetic')
    expect(route.request().postDataJSON().message).toBe('求解 x+1=2')
    submitted = true
    await route.fulfill({ status: 202, json: { success: true, job_id: 'run-demo', status: 'queued' } })
  })
  await page.route('**/api/agent/jobs/run-demo/report', route => route.fulfill({ json: { ...report, evidence_id: 'run-demo' } }))
  await page.goto('/dashboard-assets/')
  await expect(page.locator('[data-workspace="conversation-workbench"]')).toBeVisible()
  await expect(page.locator('.workspace-shell')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: '把题干交给一组会互相质疑的子智能体' })).toBeVisible()
  await page.locator('#math-question').fill('求解 x+1=2')
  await page.getByRole('button', { name: '开始求解', exact: true }).click()
  await expect(page.getByRole('region', { name: '对话式执行工作台' })).toBeVisible()
  await expect(page.locator('.workbench-problem')).toContainText('求解 x+1=2')
  expect(creations).toBe(1)
  await page.screenshot({ path: '../../../artifacts/workbench-full-page.png', fullPage: true })
})
const progress = { plan_version: 1, attempt_index: 0, steps: [
  { label: '步骤 1', reported: true, current: false, verdict: 'ACCEPT', valid: true },
  { label: '步骤 2', reported: true, current: true, verdict: 'CHALLENGE', valid: false },
] }
const message = { version: 'workbench-v1', thread_id: 'thread-shared', content_status: 'not_published',
  thread_status: 'open', plan_version: 1, attempt_index: 0, step_label: '步骤 2' }
const stream = frame(1, 'solver_progress', { solver_event_type: 'initial_plan_generated', role: 'planner',
  solver_revision: 1, solver: { progress }, evidence_kind: 'scripted' })
  + frame(2, 'solver_progress', { solver_event_type: 'step_reviewed', role: 'step_verifier',
    workbench: { ...message, message_id: 'message-a', from_role: 'step_verifier', to_role: 'reasoner', kind: 'challenge', summary: '检查边界条件' } })
  + frame(2, 'solver_progress', { solver_event_type: 'step_reviewed', role: 'step_verifier' })
  + frame(3, 'solver_progress', { solver_event_type: 'meta_dispatched', role: 'meta' })
  + frame(4, 'solver_progress', { solver_event_type: 'challenge_replied', role: 'reasoner',
    workbench: { ...message, message_id: 'message-b', from_role: 'reasoner', to_role: 'step_verifier', kind: 'reply', summary: '回复已记录' } })
  + frame(5, 'final_result', { data: { summary: '运行说明不是答案' } })
  + frame(6, 'presentation_artifact_saved', {})

for (const width of [320, 768, 1024, 1440]) {
  test(`conversation shares plan, threads and views at ${width}px`, async ({ page }) => {
    let creations = 0
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    await page.setViewportSize({ width, height: 1000 })
    await mockWorkspace(page, true, stream)
    await page.route('**/api/agent/jobs', async route => {
      creations += 1
      await route.fulfill({ status: 202, json: { success: true, job_id: 'run-demo', status: 'queued' } })
    })
    await page.route('**/api/agent/jobs/run-demo/report', route => route.fulfill({ json: { ...report, evidence_id: 'run-demo' } }))
    await page.goto('/dashboard-assets/session/session-demo')
    const workbench = page.getByRole('region', { name: '对话式执行工作台' })
    await expect(workbench.locator('[data-workbench-event]')).toHaveCount(6)
    await expect(workbench.locator('[data-thread-id="thread-shared"] article')).toHaveCount(2)
    await expect(workbench.locator('[data-step-status="pass"]')).toHaveCount(1)
    await expect(workbench.getByText('FAKE · 模拟数据')).toBeVisible()
    await workbench.getByRole('button', { name: '完整星图', exact: true }).click()
    await expect(workbench.locator('.constellation:not(.mini)')).toBeVisible()
    await workbench.getByRole('button', { name: '筛选推理角色' }).first().click()
    await workbench.getByRole('button', { name: '对话事件', exact: true }).click()
    await expect(workbench.locator('[data-workbench-event]:visible')).toHaveCount(2)
    await workbench.getByRole('button', { name: '清除筛选' }).click()
    await expect(workbench.locator('[data-workbench-event]:visible')).toHaveCount(6)
    expect(await workbench.locator('[data-workbench-event]').evaluateAll(nodes => nodes.map(node => node.getAttribute('data-workbench-event')))).toEqual(['1', '2', '3', '4', '5', '6'])
    await workbench.getByRole('slider').fill('4')
    await expect(workbench.locator('.message-wire')).toHaveCount(2)
    await workbench.getByRole('slider').fill('0')
    await expect(workbench.locator('.message-wire')).toHaveCount(0)
    await workbench.getByRole('button', { name: '返回任务状态' }).click()
    await workbench.getByRole('button', { name: '深色主题', exact: true }).click()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    await workbench.getByRole('button', { name: '浅色主题', exact: true }).click()
    expect(creations).toBe(0)
    expect(errors).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await workbench.screenshot({ path: `../../../artifacts/workbench-${width}.png` })
  })
}
