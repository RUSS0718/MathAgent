import { test, expect } from '@playwright/test'
import { mockWorkspace } from './fixtures'
test('dropped response reload and another tab recover without another POST', async ({ page, context }) => {
  let posts = 0
  let accepted: string | undefined
  async function setup(target: typeof page) {
    await mockWorkspace(target)
    await target.route('**/api/agent/submissions/*', route => route.fulfill(accepted
      ? { json: { success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'succeeded' } }
      : { status: 404, json: { code: 'job_not_found' } }))
    await target.route('**/api/agent/jobs', async route => {
      posts++; accepted = route.request().headers()['idempotency-key']
      await route.abort('failed')
    })
  }
  await setup(page)
  await page.goto('/dashboard-assets/session/session-demo')
  await page.locator('#math-question').fill('2+3')
  await page.getByRole('button', { name: '开始求解', exact: true }).click()
  await expect(page.locator('.notice')).toContainText('核对')
  await page.reload()
  await expect(page.getByRole('region', { name: '对话式执行工作台' })).toBeVisible()
  const second = await context.newPage()
  await setup(second)
  await second.goto('/dashboard-assets/session/session-demo')
  await expect(second.getByRole('region', { name: '对话式执行工作台' })).toBeVisible()
  expect(posts).toBe(1)
  expect(accepted).toBeTruthy()
})

test('two tabs clicking together share one pending submission and dispatch', async ({ page, context }) => {
  let posts = 0
  let accepted = false
  for (const target of [page, await context.newPage()]) {
    await mockWorkspace(target)
    await target.route('**/api/agent/submissions/*', route => route.fulfill(accepted
      ? { json: { success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'succeeded' } }
      : { status: 404, json: { code: 'job_not_found' } }))
    await target.route('**/api/agent/jobs', async route => {
      posts++; accepted = true
      await route.fulfill({ json: { success: true, job_id: 'run-demo', status: 'succeeded' } })
    })
    await target.goto('/dashboard-assets/session/session-demo')
    await target.locator('#math-question').fill('2+3')
  }
  await Promise.all(context.pages().map(target => target.getByRole('button', { name: '开始求解', exact: true }).click()))
  for (const target of context.pages()) await expect(target.getByRole('region', { name: '对话式执行工作台' })).toBeVisible()
  expect(posts).toBe(1)
})

test('pending input conflict blocks dispatch and explicit re-solve uses a fresh identity', async ({ page }) => {
  await mockWorkspace(page)
  const keys: string[] = []
  await page.route('**/api/agent/submissions/*', route => route.fulfill({ status: 404, json: { code: 'job_not_found' } }))
  await page.route('**/api/new_chat', route => route.fulfill({ json: { success: true, new_session_id: 'session-fresh' } }))
  await page.route('**/api/agent/jobs', async route => {
    keys.push(route.request().headers()['idempotency-key']!)
    await route.abort('failed')
  })
  await page.goto('/dashboard-assets/session/session-demo')
  await page.locator('#math-question').fill('2+3')
  await page.getByRole('button', { name: '开始求解', exact: true }).click()
  await expect(page.locator('.notice')).toContainText('核对')
  await page.locator('#math-question').fill('2+4')
  await page.getByRole('button', { name: '开始求解', exact: true }).click()
  await expect(page.locator('.notice')).toContainText('冲突')
  expect(keys).toHaveLength(1)
  await page.getByRole('button', { name: '再次求解', exact: true }).click()
  await expect(page.locator('#math-question')).toHaveValue('2+4')
  await page.getByRole('button', { name: '开始求解', exact: true }).click()
  await expect.poll(() => keys.length).toBe(2)
  expect(keys[0]).not.toBe(keys[1])
})
