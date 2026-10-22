import { expect, test } from '@playwright/test'
import { mockWorkspace } from './fixtures'

test('Shift Enter adds a line and Enter submits only once', async ({ page }) => {
  await mockWorkspace(page)
  let requests = 0
  page.on('request', request => { if (new URL(request.url()).pathname === '/api/agent/jobs') requests++ })
  await page.goto('/dashboard-assets/session/session-demo')
  const input = page.getByRole('textbox', { name: '数学问题' })
  await input.fill('求解')
  await input.press('Shift+Enter')
  await expect(input).toHaveValue('求解\n')
  expect(requests).toBe(0)
  await input.press('Enter')
  await expect(input).toHaveValue('')
  expect(requests).toBe(1)
})

test('loading and failed settings stay recoverable', async ({ page }) => {
  await mockWorkspace(page)
  let release: () => void = () => {}
  const gate = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/capabilities', async route => {
    await gate
    await route.fulfill({ status: 503, json: { error: '配置暂不可用' } })
  })
  await page.goto('/dashboard-assets/settings')
  await expect(page.getByRole('status')).toContainText('正在读取配置')
  await expect(page.getByRole('button', { name: '刷新状态' })).toBeDisabled()
  release()
  await expect(page.getByRole('alert')).toContainText('配置暂不可用')
  await expect(page.getByRole('button', { name: '刷新状态' })).toBeEnabled()
})

test('campaign and evidence exports produce named JSON downloads', async ({ page }) => {
  await mockWorkspace(page, true)
  await page.goto('/dashboard-assets/campaigns?campaign=campaign-demo')
  const campaignDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出当前公开报告 JSON' }).click()
  expect((await campaignDownload).suggestedFilename()).toBe('campaign-demo.json')
  await page.goto('/dashboard-assets/run/run-demo')
  const evidenceDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出公开 Evidence JSON' }).click()
  expect((await evidenceDownload).suggestedFilename()).toBe('run-demo-evidence.json')
})

test('failed Run remains explicit and cannot be canceled again', async ({ page }) => {
  await mockWorkspace(page)
  await page.route('**/api/agent/jobs/run-demo', route => route.fulfill({ json: { success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'failed', error: 'transport_timeout' } }))
  await page.route('**/api/agent/jobs/run-demo/report', route => route.fulfill({ status: 503, json: { error: '报告暂不可用' } }))
  await page.goto('/dashboard-assets/run/run-demo')
  await expect(page.getByRole('heading', { name: '报告当前不可用' })).toBeVisible()
  await expect(page.getByRole('button', { name: '取消 Run' })).toBeDisabled()
  await expect(page.getByRole('button', { name: '刷新持久报告' })).toBeEnabled()
})
