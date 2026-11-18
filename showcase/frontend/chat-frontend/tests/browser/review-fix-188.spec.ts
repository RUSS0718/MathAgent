import { expect, test } from '@playwright/test'
import { mockWorkspace } from './fixtures'

test('ordinary resume failure displays a readable notice without internal codes', async ({ page }) => {
  await mockWorkspace(page, true, '')
  await page.route('**/api/agent/jobs/run-demo', r => r.fulfill({ json: {
    success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'waiting_input',
    result: { faithful: { phase: 'paused', allowed_actions: ['resume_intervention'] } },
  } }))
  await page.route('**/api/agent/jobs/run-demo/interventions/resume', r => r.fulfill({ json: {
    success: false, error: 'intervention_parent_pause_identity_mismatch',
  } }))
  await page.goto('/dashboard-assets/session/session-demo')
  await page.getByRole('button', { name: '恢复执行', exact: true }).click()
  await expect(page.locator('.notice').first()).toContainText('恢复请求未能确认，请刷新任务状态。')
  await expect(page.locator('body')).not.toContainText('intervention_parent_pause_identity_mismatch')
})

test('ordinary dedicated resume and pause controls use their actual HTTP endpoints', async ({ page }) => {
  await mockWorkspace(page, true, '')
  let action = 'pause'
  let pauses = 0; let resumes = 0
  await page.route('**/api/agent/jobs/run-demo', r => r.fulfill({ json: {
    success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'waiting_input',
    result: { execution_mode: 'fake', faithful: { phase: action === 'pause' ? 'running' : 'paused', allowed_actions: [action] } },
  } }))
  await page.route('**/api/agent/jobs/run-demo/interventions/pause', r => { pauses++; action = 'resume_intervention'; return r.fulfill({ json: { success: true } }) })
  await page.route('**/api/agent/jobs/run-demo/interventions/resume', r => { resumes++; expect(r.request().headers()['idempotency-key']).toBeTruthy(); return r.fulfill({ json: { success: true, status: 'queued' } }) })
  await page.goto('/dashboard-assets/session/session-demo')
  await expect(page.getByText('模拟运行', { exact: false })).toBeVisible()
  await page.getByRole('button', { name: '请求安全暂停' }).click()
  await page.getByRole('button', { name: '恢复执行', exact: true }).click()
  expect(pauses).toBe(1); expect(resumes).toBe(1)
})

test('terminal transition restarts answer reads after the observation limit', async ({ page }) => {
  await page.clock.install()
  await mockWorkspace(page, true, '')
  let terminal = false; let reads = 0
  const mutations: string[] = []
  page.on('request', r => { if (r.method() === 'POST' && r.url().includes('/run-demo')) mutations.push(r.url()) })
  await page.route('**/api/agent/jobs/run-demo', r => r.fulfill({ json: {
    success: true, job_id: 'run-demo', session_id: 'session-demo', status: terminal ? 'succeeded' : 'waiting_input',
    result: { faithful: { phase: 'unknown', allowed_actions: [] } },
  } }))
  await page.route('**/api/agent/jobs/run-demo/answer', r => { reads++; return r.fulfill({ json: {
    job_id: 'run-demo', status: terminal ? 'succeeded' : 'waiting_input', mode: 'solve',
    presentation_status: terminal ? 'ready' : 'pending', answer: terminal ? '迟到的唯一答复' : '', notice: '',
  } }) })
  await page.goto('/dashboard-assets/session/session-demo')
  await expect(page.getByRole('region', { name: '最终答复' })).toBeVisible()
  for (let i = 0; i < 92; i++) { await page.clock.runFor(2100); await page.waitForTimeout(1) }
  await expect(page.getByRole('button', { name: '重新读取答复' })).toBeVisible()
  const before = reads; terminal = true
  await page.getByRole('button', { name: '刷新任务状态' }).click()
  await expect(page.getByRole('region', { name: '最终答复' })).toContainText('迟到的唯一答复')
  expect(reads).toBeGreaterThan(before); expect(mutations).toEqual([])
})
