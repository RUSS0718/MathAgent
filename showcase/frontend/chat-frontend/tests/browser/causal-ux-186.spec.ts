import { expect, test } from '@playwright/test'
import { mockWorkspace, report } from './fixtures'

const frame = (id: number, extra: Record<string, unknown>) => `id: ${id}\nevent: solver_progress\ndata: ${JSON.stringify({ type: 'solver_progress', ...extra })}\n\n`
for (const width of [390, 1440]) {
  for (const status of ['running', 'succeeded', 'waiting_input', 'failed', 'canceled']) {
    test(`causal UX ${status} at ${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1000 })
      const errors: string[] = []
      const posts: string[] = []
      page.on('pageerror', error => errors.push(error.message))
      page.on('request', request => { if (request.method() === 'POST' && request.url().includes('/agent/jobs')) posts.push(request.url()) })
      const stream = frame(1, { solver_event_type: 'initial_plan_generated', role: 'planner', plan_version: 1 })
        + Array.from({ length: 2000 }, (_, i) => frame(i + 2, { solver_event_type: 'state_saved', role: 'controller', summary: 'PRIVATE' })).join('')
        + frame(2002, { solver_event_type: 'call_audit', role: 'reasoner', solver_call_id: 'call-one', call_lifecycle: 'running', created_at: new Date().toISOString() })
      await mockWorkspace(page, true, stream + stream)
      const result = { execution_mode: 'fake', faithful: { version: 'faithful-task-v1', phase: status === 'failed' ? 'unknown' : status === 'succeeded' ? 'completed' : status, allowed_actions: [] }, identity: { attempt_id: 'attempt-one' }, budget: { used: 1 } }
      await page.route('**/api/agent/jobs/run-demo', route => route.fulfill({ json: { success: true, job_id: 'run-demo', session_id: 'session-demo', status, last_event_id: 0, result } }))
      await page.route('**/api/agent/jobs/run-demo/report', route => status === 'succeeded'
        ? route.fulfill({ json: report }) : route.fulfill({ status: 409, json: { error: 'not_ready' } }))
      await page.route('**/api/agent/jobs/run-demo/answer', route => route.fulfill({ json: {
        job_id: 'run-demo', status, mode: 'solve', presentation_status: 'ready',
        answer: status === 'succeeded' ? report.report.answer : '', notice: '模拟答复，候选检查。'
      } }))
      await page.goto('/dashboard-assets/session/session-demo')
      const process = page.locator('.execution-process')
      await expect(process).toHaveAttribute('open', '')
      if (['succeeded', 'failed', 'canceled'].includes(status)) {
        if (status === 'succeeded') {
          await expect(page.getByRole('region', { name: '最终答复' })).toContainText('模拟答复，候选检查。')
          expect(await page.locator('.report-section').evaluate(el => Boolean(el.compareDocumentPosition(document.querySelector('.execution-process')!) & Node.DOCUMENT_POSITION_FOLLOWING))).toBe(true)
        }
      }
      const workbench = page.getByRole('region', { name: '对话式执行工作台' })
      await workbench.getByRole('button', { name: '关键进展', exact: true }).click()
      await expect(workbench.locator('.conversation-events > li')).toHaveCount(1)
      await expect(workbench.getByText('求解计划已形成', { exact: true })).toBeVisible()
      await expect(workbench.getByText(/技术详情/)).toHaveCount(0)
      await expect(workbench).not.toContainText('PRIVATE')
      await expect(workbench.locator('.message-flight')).toHaveCount(0)
      await expect(workbench.locator('.mini [data-role-state="running"]')).toHaveCount(status === 'running' ? 1 : 0)
      await page.locator('.constellation-page').evaluate(el => { el.scrollTop = 0 })
      await page.screenshot({ path: `../../../artifacts/ux-186/${status}-${width}.png` })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      await page.reload()
      await expect(page.locator('.workbench-problem')).toBeVisible()
      expect(posts).toEqual([])
      expect(errors).toEqual([])
    })
  }
}

test('fresh batch handoffs are bounded, reduced motion is respected, and replay does not steal reading position', async ({ page }) => {
  const stream = Array.from({ length: 12 }, (_, i) => frame(i + 1, { solver_event_type: 'step_reported', role: 'reasoner', step_id: `步骤 ${i + 1}`,
    workbench: { version: 'workbench-v1', thread_id: `thread-${i}`, message_id: `message-${i}`, from_role: 'reasoner', to_role: 'step_verifier',
      kind: 'reply', summary: '步骤结果已提交', content_status: 'not_published', thread_status: 'open', plan_version: 1, attempt_index: 0 } })).join('')
  await mockWorkspace(page, false, stream)
  await page.route('**/api/agent/jobs/run-demo', route => route.fulfill({ json: { success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'running', last_event_id: 0 } }))
  await page.route('**/api/agent/jobs/run-demo/report', route => route.fulfill({ status: 409, json: { error: 'not_ready' } }))
  await page.route('**/api/agent/jobs', route => route.fulfill({ status: 202, json: { success: true, job_id: 'run-demo', status: 'running' } }))
  await page.goto('/dashboard-assets/')
  await page.locator('#math-question').fill('受控交接显示测试')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  const workbench = page.getByRole('region', { name: '对话式执行工作台' })
  await expect(workbench.locator('.conversation-events > li')).toHaveCount(6)
  await workbench.getByRole('button', { name: '完整星图', exact: true }).click()
  await expect(workbench.locator('.message-wire')).toBeVisible()
  await expect(workbench.locator('[data-flight]')).toHaveCount(0)
  await workbench.getByRole('button', { name: '关键进展', exact: true }).click()
  await workbench.getByText('查看历史回放', { exact: true }).click()
  await workbench.getByRole('slider').fill('5')
  await workbench.getByRole('button', { name: '回放已收事件', exact: true }).click()
  await page.locator('.constellation-page').evaluate(el => { el.scrollTop = 0 })
  await expect(workbench.locator('.conversation-events > li')).toHaveCount(6)
  expect(await page.locator('.constellation-page').evaluate(el => el.scrollTop)).toBeLessThan(50)
  await workbench.getByRole('button', { name: '暂停回放', exact: true }).click()
})

test('completed history keeps progress after an earlier answered interruption', async ({ page }) => {
  const stream = 'id: 1\nevent: interrupt\ndata: {"type":"interrupt","job_id":"run-demo","status":"waiting_input"}\n\n'
    + 'id: 2\nevent: resumed\ndata: {"type":"resumed"}\n\n'
    + frame(3, { solver_event_type: 'initial_plan_generated', role: 'planner' })
    + 'id: 4\nevent: final_result\ndata: {"type":"final_result","data":{}}\n\n'
  await mockWorkspace(page, true, stream)
  await page.goto('/dashboard-assets/session/session-demo')
  await page.getByRole('button', { name: '关键进展', exact: true }).click()
  const workbench = page.locator('.workbench')
  await expect(workbench.getByText('执行完成，请查看答案和实际检查结论')).toBeVisible()
  await expect(workbench.getByText('求解计划已形成')).toBeVisible()
  await expect(workbench.locator('.message-flight')).toHaveCount(0)
})
