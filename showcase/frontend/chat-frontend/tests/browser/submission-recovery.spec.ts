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
    await target.route('**/api/load_session?*', route => route.fulfill({ json: { success: true,
      messages: accepted ? [{ sender: 'user', text: '2+3', analysis_job_id: 'run-demo' }] : [],
    } }))
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

test('recovery lookup exposes busy semantics', async ({ page }) => {
  await mockWorkspace(page)
  await page.route('**/api/agent/jobs', route => route.abort('failed'))
  await page.goto('/dashboard-assets/session/session-demo')
  await page.locator('#math-question').fill('2+3')
  await page.getByRole('button', { name: '开始求解', exact: true }).click()
  await expect(page.locator('.notice')).toContainText('核对')
  let release!: () => void
  const pending = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/agent/submissions/*', async route => {
    await pending
    await route.fulfill({ status: 404, json: { code: 'job_not_found' } })
  })
  await page.getByRole('button', { name: '核对原提交', exact: true }).click()
  try {
    const button = page.getByRole('button', { name: '正在核对…', exact: true })
    await expect(button).toBeDisabled()
    await expect(button).toHaveAttribute('aria-busy', 'true')
  } finally { release() }
  await expect(page.getByRole('button', { name: '开始求解', exact: true })).not.toHaveAttribute('aria-busy', 'true')
})

test('re-solving an accepted submission preserves its input after reload', async ({ page }) => {
  await mockWorkspace(page)
  await page.route('**/api/capabilities', route => route.fulfill({ json: {
    profile: 'showcase', jobs: { enabled: true, status: 'available' }, sse: { enabled: true, status: 'available' },
    verification_mode: ['auto'], files: { upload: { enabled: true } },
    capabilities: { jobs: true, sse: true, verification_mode: ['auto'], file_upload: { enabled: true } },
    solver_modes: [{ solver_mode: 'star_limited', enabled: true, missing_capabilities: [] }],
    presentation: { enabled: true, modes: ['teach'], status: 'available' },
  } }))
  const file = { file_id: 'image-demo', reference: 'diagram.png', mime: 'image/png', size: 8, sha256: 'demo', status: 'ready' }
  await page.route('**/api/files', route => route.fulfill({ json: [file] }))
  await page.route('**/api/upload_file', route => route.fulfill({ json: { file } }))
  await page.route('**/api/new_chat', route => route.fulfill({ json: { success: true, new_session_id: 'session-fresh' } }))
  await page.route('**/api/agent/submissions/*', route => route.fulfill({ json: {
    success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'succeeded',
  } }))
  const requests: { key: string; body: Record<string, unknown> }[] = []
  await page.route('**/api/agent/jobs', async route => {
    requests.push({ key: route.request().headers()['idempotency-key']!, body: route.request().postDataJSON() })
    await route.fulfill({ json: { success: true, job_id: 'run-demo', status: 'succeeded' } })
  })
  await page.goto('/dashboard-assets/session/session-demo')
  await page.locator('#solver-mode').selectOption('star_limited')
  await page.locator('input[type=file]').setInputFiles({ name: 'diagram.png', mimeType: 'image/png', buffer: Buffer.alloc(8) })
  await expect(page.getByRole('button', { name: '移除题图' })).toBeVisible()
  await page.locator('#math-question').fill('/teach 证明图中的角相等')
  await page.getByRole('button', { name: '开始求解', exact: true }).click()
  await expect.poll(() => requests.length).toBe(1)
  const input = { message: '证明图中的角相等', input_user_file_id: 'image-demo', presentation_mode: 'teach', solver_mode: 'star_limited' }
  expect(requests[0].body).toMatchObject({ ...input, session_id: 'session-demo' })
  await page.reload()
  await expect(page.getByRole('region', { name: '对话式执行工作台' })).toBeVisible()
  await page.getByRole('button', { name: '再次求解', exact: true }).click()
  await expect(page.locator('#math-question')).toHaveValue('/teach 证明图中的角相等')
  await expect(page.getByRole('button', { name: '移除题图' })).toBeVisible()
  await expect(page.locator('#solver-mode')).toHaveValue('star_limited')
  await page.getByRole('button', { name: '开始求解', exact: true }).click()
  await expect.poll(() => requests.length).toBe(2)
  expect(requests[1].body).toMatchObject({ ...input, session_id: 'session-fresh' })
  expect(requests[1].key).not.toBe(requests[0].key)
})
