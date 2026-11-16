import { expect, test } from '@playwright/test'
import { mockWorkspace } from './fixtures'

test('196 ordinary input has IME-safe keyboard command chips', async ({ page }) => {
  await mockWorkspace(page)
  await page.route('**/api/capabilities', r => r.fulfill({ json: { profile: 'showcase', execution: { mode: 'fake', provider: 'demo', status: 'available' }, jobs: { enabled: true, status: 'available' }, sse: { enabled: true, status: 'available' }, verification_mode: ['auto'], files: { upload: { enabled: false } }, presentation: { enabled: true, modes: ['solve', 'teach', 'report'], status: 'available' }, capabilities: { jobs: true, sse: true, verification_mode: ['auto'], file_upload: { enabled: false } } } }))
  await page.goto('/dashboard-assets/session/session-demo')
  const input = page.getByRole('textbox', { name: '数学问题' })
  await input.fill('/')
  await expect(page.getByRole('listbox', { name: '答复规则' })).toBeVisible()
  await input.dispatchEvent('keydown', { key: 'Enter', isComposing: true })
  await expect(page.getByRole('listbox', { name: '答复规则' })).toBeVisible()
  await input.press('ArrowDown')
  await input.press('Enter')
  await expect(page.getByRole('button', { name: '移除教学规则' })).toBeVisible()
  await expect(input).toHaveValue('')
  await input.press('Backspace')
  await expect(page.getByRole('button', { name: '移除教学规则' })).toHaveCount(0)
  await expect(page.getByText('生成模板', { exact: false })).toHaveCount(0)
})
for (const mode of ['solve', 'teach', 'report']) test(`196 ${mode} freezes command in submission and history`, async ({ page }) => {
  await mockWorkspace(page)
  let submitted = false
  let count = 0
  await page.route('**/api/capabilities', async route => {
    await route.fulfill({ json: { profile: 'showcase', jobs: { enabled: true, status: 'available' }, sse: { enabled: true, status: 'available' }, verification_mode: ['auto'], files: { upload: { enabled: false } }, presentation: { enabled: true, status: 'available', modes: ['solve', 'teach', 'report'] }, capabilities: { jobs: true, sse: true, verification_mode: ['auto'], file_upload: { enabled: false } } } })
  })
  await page.route('**/api/load_session?*', route => route.fulfill({ json: { success: true, messages: submitted ? [{ sender: 'user', text: '证明示例', analysis_job_id: 'run-demo' }, { sender: 'ai', text: '不应重复显示的旧答案', analysis_job_id: 'run-demo' }] : [] } }))
  await page.route('**/api/agent/jobs', route => {
    expect(route.request().postDataJSON().presentation_mode).toBe(mode)
    expect(route.request().postDataJSON().message).toBe('证明示例')
    count++; submitted = true
    return route.fulfill({ json: { success: true, job_id: 'run-demo', status: 'succeeded' } })
  })
  await page.route('**/api/agent/jobs/run-demo', route => route.fulfill({ json: { success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'succeeded', result: { presentation_mode: mode } } }))
  await page.route('**/api/agent/jobs/run-demo/answer', route => route.fulfill({ json: { job_id: 'run-demo', status: 'succeeded', mode, answer: '唯一答复', presentation_status: 'ready', notice: '' } }))
  await page.goto('/dashboard-assets/session/session-demo')
  const input = page.getByRole('textbox', { name: '数学问题' })
  await input.fill('/' + mode)
  await input.press('Enter')
  await input.fill('证明示例')
  await input.press('Enter')
  await expect(page.getByRole('region', { name: '最终答复' })).toContainText('唯一答复')
  await page.reload()
  await expect(page.getByRole('region', { name: '最终答复' })).toContainText('唯一答复')
  await expect(page.getByText('不应重复显示的旧答案')).toHaveCount(0)
  expect(count).toBe(1)
})
