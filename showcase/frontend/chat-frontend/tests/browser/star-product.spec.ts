import { expect, test, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

async function create(page: Page, problem: string, origin = '', mode = 'star_limited') {
  await page.goto('/dashboard-assets/')
  const auth = await (await page.request.get(origin + '/api/check_auth')).json()
  const headers = { 'X-CSRF-Token': auth.csrf_token, 'Idempotency-Key': crypto.randomUUID() }
  const session = await (await page.request.post(origin + '/api/new_chat', { headers })).json()
  const response = await page.request.post(origin + '/api/agent/jobs', { headers, data: { message: problem, session_id: session.new_session_id, solver_mode: mode } })
  expect(response.status()).toBe(202)
  return (await response.json()).job_id as string
}
async function terminal(page: Page, id: string, origin = '') {
  await expect.poll(async () => (await (await page.request.get(`${origin}/api/agent/jobs/${id}`)).json()).status, { timeout: 15000 }).toMatch(/succeeded|failed|canceled/)
}
async function count(page: Page, id: string) { return (await (await page.request.get('http://127.0.0.1:8092')).json())[id] }

for (const width of [320, 768, 1024, 1440]) {
  test(`persistent product review and read-only controls ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 })
    const errors: string[] = []
    page.on('pageerror', e => errors.push(e.message))
    const id = await create(page, 'plan')
    await terminal(page, id)
    await page.goto(`/dashboard-assets/run/${id}`)
    await expect(page.getByRole('heading', { name: 'STAR 持久进展' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '报告当前不可用' })).toHaveCount(0)
    await expect(page.getByText('fault_injection', { exact: true })).toBeVisible()
    await expect(page.getByText('步骤 1', { exact: false }).first()).toBeVisible()
    const before = await count(page, id)
    expect(before).toBe(6)
    await page.reload()
    await page.getByRole('button', { name: '刷新持久报告' }).click()
    await page.getByRole('button', { name: '重连事件（沿用游标）' }).click()
    await page.getByRole('button', { name: '零调用重放候选选择' }).click()
    await expect(page.getByText('只重放已保存状态，不启动模型或工具。')).toBeVisible()
    const download = page.waitForEvent('download')
    await page.getByRole('button', { name: '导出公开 Evidence JSON' }).click()
    expect((await download).suggestedFilename()).toContain(id)
    await Promise.all([page.request.get(`/api/runs/${id}/evidence`), page.request.get(`/api/agent/jobs/${id}/report`)])
    expect(await count(page, id)).toBe(before)
    const text = await page.locator('body').innerText()
    expect(text).not.toContain('PRIVATE HINT TEXT')
    expect(text).not.toContain('PRIVATE PROOF TEXT')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
    expect(errors).toEqual([])
    await page.screenshot({ path: info.outputPath(`product-${width}.png`), fullPage: true })
  })
}

test('unknown is never automatically retried and explicit retry updates the same Run', async ({ page }) => {
  const id = await create(page, 'unknown')
  await terminal(page, id)
  await page.goto(`/dashboard-assets/run/${id}`)
  const action = page.getByRole('button', { name: '明确选择：用新身份重试' })
  await expect(action).toBeVisible()
  expect(await count(page, id)).toBe(1)
  await page.reload()
  await expect(action).toBeVisible()
  expect(await count(page, id)).toBe(1)
  await action.click()
  await expect(page.getByText('succeeded', { exact: true }).first()).toBeVisible()
  expect(await count(page, id)).toBe(4)
})

test('cancel actual in-flight request stays canceled', async ({ page }) => {
  const id = await create(page, 'cancel')
  await page.goto(`/dashboard-assets/run/${id}`)
  await page.getByRole('button', { name: '取消 Run' }).click()
  await expect(page.getByText('canceled', { exact: true }).first()).toBeVisible()
  await page.reload()
  await expect(page.getByText('canceled', { exact: true }).first()).toBeVisible()
  expect(await count(page, id)).toBe(1)
})

test('trace-back invalidation and rescue are persisted and visible', async ({ page }) => {
  const id = await create(page, 'trace')
  await terminal(page, id)
  await page.goto(`/dashboard-assets/run/${id}`)
  await expect(page.getByText('trace_back · 原计划 1 · 尝试 0 · 失效 2 项 · 救援 1 项')).toBeVisible()
  await expect(page.getByText('回退至步骤 2 · 失效 2 项 · 救援 1 项')).toBeVisible()
  expect(await count(page, id)).toBe(18)
})

test('limited Best-Effort preserves original candidate and honest replay without calls', async ({ page }) => {
  const origin = 'http://127.0.0.1:8093'
  const id = await create(page, 'best', origin, 'star_limited_best_effort')
  await terminal(page, id, origin)
  await page.goto(`${origin}/dashboard/run/${id}`)
  await expect(page.getByText('star_limited_best_effort', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('candidate_selected', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '零调用重放候选选择' }).click()
  await expect(page.getByText('只重放已保存状态，不启动模型或工具。')).toBeVisible()
  expect(await count(page, id)).toBe(1)
})

test('deadline is displayed as failure and never as empty success', async ({ page }) => {
  const origin = 'http://127.0.0.1:8094'
  const id = await create(page, 'timeout', origin)
  await terminal(page, id, origin)
  await page.goto(`${origin}/dashboard/run/${id}`)
  await expect(page.getByText('failed', { exact: true }).first()).toBeVisible()
  await expect(page.getByRole('heading', { name: '报告当前不可用' })).toHaveCount(0)
  expect(await count(page, id)).toBe(1)
})

test('replan summary follows the actual active plan and rescued results', async ({ page }) => {
  const id = await create(page, 'replan')
  await terminal(page, id)
  await page.goto(`/dashboard-assets/run/${id}`)
  await expect(page.getByText('replan · 原计划 1 · 尝试 1 · 失效 0 项 · 救援 1 项')).toBeVisible()
  await expect(page.getByText('计划版本 2 · 尝试 2 · Meta 裁定 APPROVE_REPLAN')).toBeVisible()
  expect(await count(page, id)).toBe(18)
})

test('no candidate remains an explicit unresolved result', async ({ page }) => {
  const origin = 'http://127.0.0.1:8093'
  const id = await create(page, 'plan', origin, 'star_limited_best_effort')
  await terminal(page, id, origin)
  await page.goto(`${origin}/dashboard/run/${id}`)
  await expect(page.getByText('尚无完整候选记录；不能据此判断求解成功。')).toBeVisible()
  await expect(page.getByText('failed', { exact: true }).first()).toBeVisible()
  expect(await count(page, id)).toBe(1)
})

test('real registry receipt remains finite scope and non-resolvable refs are honest', async ({ page }) => {
  const id = await create(page, 'tool')
  await terminal(page, id)
  await page.goto(`/dashboard-assets/run/${id}`)
  await expect(page.getByText('无可解析的内容寻址产物；普通引用不代表已保存执行内容。')).toBeVisible()
  const report = await (await page.request.get(`/api/agent/jobs/${id}/report`)).json()
  expect(report.report.tool_summaries[0].receipt.executed).toBe(true)
  expect(report.report.tool_summaries[0].receipt.source).toBe('local_precheck')
  expect(report.report.checks.status).toBe('unknown')
  expect(report.report.budget.tool_calls).toBe(1)
  expect(await page.locator('body').innerText()).not.toContain('PRIVATE HINT TEXT')
})
