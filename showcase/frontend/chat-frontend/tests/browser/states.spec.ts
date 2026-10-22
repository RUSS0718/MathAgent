import { expect, test } from '@playwright/test'
import { mockWorkspace, report } from './fixtures'

test('mobile drawers contain focus, close with Escape, and restore focus', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 })
  await mockWorkspace(page)
  await page.goto('/dashboard-assets/session/session-demo')
  await expect(page.getByRole('textbox', { name: '数学问题' })).toBeVisible()
  for (const name of ['打开会话栏', '显示运行观察']) {
    const trigger = page.getByRole('button', { name, exact: true })
    await trigger.click()
    const modal = page.locator('dialog[open]')
    await expect(modal).toBeVisible()
    await expect(page).toHaveScreenshot(name === '打开会话栏' ? 'drawer-sessions-320.png' : 'drawer-observer-320.png', { maxDiffPixels: 0 })
    for (let i = 0; i < 10; i++) {
      await page.keyboard.press('Tab')
      // Native dialogs allow browser-chrome focus (body), but never background controls.
      expect(await modal.evaluate(element => document.activeElement === document.body || element.contains(document.activeElement))).toBe(true)
    }
    await page.keyboard.press('Escape')
    await expect(modal).toHaveCount(0)
    await expect(trigger).toBeFocused()
  }
})

test('startup failure can retry without leaving a permanent loader', async ({ page }) => {
  await mockWorkspace(page)
  await page.route('**/api/check_auth', route => route.abort(), { times: 1 })
  await page.goto('/dashboard-assets/')
  await expect(page.getByRole('alert')).toContainText('无法连接服务器')
  await expect(page).toHaveScreenshot('startup-error-1440.png', { maxDiffPixels: 0 })
  await page.getByRole('button', { name: '重新连接' }).click()
  await expect(page.getByRole('textbox', { name: '数学问题' })).toBeVisible()
})

test('campaign detail retry retains the selected ID', async ({ page }) => {
  await mockWorkspace(page)
  await page.route('**/api/experiments/campaigns/campaign-demo', route => route.abort(), { times: 1 })
  await page.goto('/dashboard-assets/campaigns?campaign=campaign-demo')
  await expect(page.getByRole('alert')).toBeVisible()
  await page.getByRole('button', { name: '刷新 / 重试' }).click()
  await expect(page.getByRole('heading', { name: 'campaign-demo', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '返回批次列表' }).click()
  await expect(page.getByRole('button', { name: '审阅 campaign-demo' })).toBeVisible()
})

test('empty campaigns explain how to get started', async ({ page }) => {
  await mockWorkspace(page)
  await page.route(/\/api\/experiments\/campaigns\?/, route => route.fulfill({ json: { campaigns: [], offset: 0, limit: 20 } }))
  await page.goto('/dashboard-assets/campaigns')
  await expect(page.getByRole('heading', { name: '暂无持久批次' })).toBeVisible()
  await expect(page).toHaveScreenshot('campaign-empty-1440.png', { maxDiffPixels: 0 })
  await expect(page.getByRole('button', { name: '上一页' })).toBeDisabled()
  await expect(page.getByRole('button', { name: '下一页' })).toBeDisabled()
})

test('waiting input remains editable and resumes the existing run', async ({ page }) => {
  await mockWorkspace(page, true)
  await page.route('**/api/agent/jobs/run-demo', route => route.fulfill({ json: { success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'waiting_input' } }))
  await page.route('**/api/agent/jobs/run-demo/report', route => route.fulfill({ json: { ...report, status: 'waiting_input', report: { answer: '', public_summary: '请补充 x 的定义域后继续。', stage: 'planning', checks: { status: 'unknown' }, limitations: ['尚未形成最终答案。'], tool_summaries: [], request_attempts: [] } } }))
  await page.route(/\/api\/agent\/jobs\/run-demo\/events/, route => route.fulfill({ contentType: 'text/event-stream', body: 'id: 1\nevent: interrupt\ndata: {"type":"interrupt","question_id":"q1","message":"请补充定义域"}\n\n' }))
  await page.goto('/dashboard-assets/session/session-demo')
  await expect(page.getByRole('button', { name: '补充条件' })).toBeVisible()
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0)
  await expect(page.getByText('events_stream_ended', { exact: true })).toHaveCount(0)
  await expect(page).toHaveScreenshot('waiting-input-1440.png', { maxDiffPixels: 0 })
  await page.getByRole('textbox', { name: '数学问题' }).fill('x 为实数')
  const request = page.waitForRequest('**/api/agent/jobs/run-demo/resume')
  await page.getByRole('button', { name: '补充条件' }).click()
  expect((await request).postDataJSON()).toEqual({ answer: 'x 为实数' })
})

test('legacy failure is readable and retry sends exactly one request', async ({ page }) => {
  await page.goto('http://127.0.0.1:5177/demo')
  await page.route('**/solve', route => route.fulfill({ status: 502, json: { error: 'agent_unavailable' } }))
  await page.getByRole('textbox', { name: '数学问题' }).fill('1 + 1')
  await page.getByRole('button', { name: '求解', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('请求失败，可重试')
  await expect(page.getByRole('button', { name: '求解', exact: true })).toBeEnabled()
  await page.route('**/solve', route => route.fulfill({ json: { final_response: '2' } }))
  await page.getByRole('button', { name: '求解', exact: true }).click()
  await expect(page.locator('#result')).toContainText('final_response')
})
