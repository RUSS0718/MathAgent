import { expect, test, type Page } from '@playwright/test'
import { mockWorkspace } from './fixtures'

// Public workbench fields only. The synthetic stream controls exactly when a handoff arrives.
function handoff(id: number, from: string, to: string, kind: string, summary: string, extra = {}, eventFields = {}) {
  return `id: ${id}\nevent: solver_progress\ndata: ${JSON.stringify({ type: 'solver_progress', evidence_kind: 'live', ...eventFields,
    workbench: { thread_id: 'public-example', message_id: `message-${id}`, from_role: from, to_role: to, kind,
      summary, plan_version: 1, attempt_index: 0, ...extra },
  })}\n\n`
}
const reasoner = 'reasoner', checker = 'step_verifier'
const earlier = handoff(1, reasoner, checker, 'reply', '提交第一步核验')
const later = handoff(2, reasoner, checker, 'reply', '已回复边界条件')
const challenge = handoff(2, checker, reasoner, 'challenge', '本步收到质疑', { content_status: 'not_published' },
  { objection_summary: '需检查零根边界' })
const rollback = handoff(3, 'controller', reasoner, 'rollback', '已退回重算')
const approval = handoff(4, 'meta', 'controller', 'decision', '', { chosen: 'CONTINUE', content_status: 'not_published' })

async function openSession(page: Page, sessionId = 'session-demo') {
  // Serve the Vite document at the ordinary session URL used by the production server.
  await page.route(`**/dashboard/session/${sessionId}`, async route => {
    const url = new URL(route.request().url())
    url.pathname = '/dashboard-assets/'
    await route.fulfill({ response: await route.fetch({ url: url.href }) })
  })
  await page.goto(`/dashboard/session/${sessionId}`)
}

async function controlledStream(page: Page, initial = '') {
  await page.addInitScript(initial => {
    const nativeFetch = window.fetch
    const encoder = new TextEncoder()
    const stream = new ReadableStream<Uint8Array>({ start(controller) {
      if (initial) controller.enqueue(encoder.encode(initial))
      Object.assign(window, { deliverHandoff: (frame: string) => controller.enqueue(encoder.encode(frame)) })
    } })
    window.fetch = (input, init) => typeof input === 'string' && /^\/api\/agent\/jobs\/run-demo\/events(?:\?|$)/.test(input)
      ? Promise.resolve(new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } })) : nativeFetch(input, init)
  }, initial)
  return (frame: string) => page.evaluate(frame => (window as Window & { deliverHandoff: (frame: string) => void }).deliverHandoff(frame), frame)
}

const messages = (page: Page) => page.getByRole('list', { name: '公开交接' })
const item = (page: Page, order: number) => messages(page).getByRole('button', { name: new RegExp(`^第 ${order} 条`) })

test('a later handoff on the same path cannot replace the open evidence', async ({ page }) => {
  await mockWorkspace(page, true)
  await page.route('**/api/agent/jobs/run-demo', route => route.fulfill({ json: {
    success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'running', last_event_id: 0,
  } }))
  const deliver = await controlledStream(page, earlier)
  const submissions: string[] = []
  page.on('request', request => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/agent/jobs') submissions.push(request.url())
  })
  await openSession(page)
  await expect(page.getByRole('region', { name: '对话式执行工作台' })).toBeVisible()
  await expect(item(page, 1)).toBeVisible()
  await item(page, 1).press('Enter')
  const detail = page.getByRole('dialog', { name: '交接依据' })
  await expect(detail).toContainText('第 1 条 · 推理 → 步骤检查 · 答复')
  await expect(detail).toContainText('提交第一步核验')
  await expect(detail.getByRole('button', { name: '关闭' })).toBeFocused()
  await deliver(later)
  await expect(item(page, 2)).toContainText('答复')
  await expect(detail).toContainText('提交第一步核验')
  await expect(detail).not.toContainText('已回复边界条件')
  await page.keyboard.press('Escape')
  await expect(item(page, 1)).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(item(page, 2)).toBeFocused()
  await page.keyboard.press('Space')
  await expect(detail).toContainText('第 2 条 · 推理 → 步骤检查 · 答复')
  await expect(detail).toContainText('已回复边界条件')
  await detail.getByRole('button', { name: '关闭' }).press('Enter')
  await expect(item(page, 2)).toBeFocused()
  expect(submissions).toEqual([])
})

test('four actions have matching arrival feedback and a static cue in reduced motion', async ({ page }, testInfo) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await mockWorkspace(page)
  let submitted = false
  await page.route('**/api/load_session?*', route => route.fulfill({ json: { success: true,
    messages: submitted ? [{ sender: 'user', text: '检查零根边界', analysis_job_id: 'run-demo' }] : [],
  } }))
  await page.route('**/api/agent/jobs', route => {
    submitted = true
    return route.fulfill({ status: 202, json: { success: true, job_id: 'run-demo', status: 'running' } })
  })
  const deliver = await controlledStream(page)
  await openSession(page)
  await page.getByRole('textbox', { name: '数学问题', exact: true }).fill('检查零根边界')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  const map = page.getByLabel('智能体协作星图', { exact: true })
  await expect(map).toBeVisible()
  await page.clock.install()
  await deliver(earlier + challenge + rollback + approval)
  await page.clock.runFor(150)
  const actions = [
    { tone: 'handoff', action: '答复', color: 'rgb(163, 187, 212)', position: ['831', '365'] },
    { tone: 'challenge', action: '质疑', color: 'rgb(255, 192, 120)', position: ['766', '175'] },
    { tone: 'rollback', action: '退回', color: 'rgb(255, 145, 160)', position: ['766', '175'] },
    { tone: 'approve', action: '通过', color: 'rgb(136, 216, 165)', position: ['500', '306'] },
  ]
  await expect(messages(page).getByRole('button')).toHaveCount(4)
  for (const [index, { tone, action, color, position }] of actions.entries()) {
    await expect(item(page, index + 1)).toContainText(action)
    const wire = map.locator(`[data-decision=${tone}] .message-wire`)
    await expect(wire).toHaveCSS('stroke', color)
    await expect(wire).toHaveCSS('stroke-dasharray', tone === 'rollback' ? '6px, 5px' : 'none')
    await expect(map.locator(`[data-decision=${tone}] .wire-label`)).toHaveText(action)
    const arrival = map.locator(`[data-flight][data-decision=${tone}] .arrival`)
    await expect(arrival).toHaveCSS('stroke', color)
    await expect(arrival).toHaveCSS('animation-name', /^arrival-/)
    await expect(arrival).toHaveAttribute('cx', position[0]!)
    await expect(arrival).toHaveAttribute('cy', position[1]!)
  }
  await page.setViewportSize({ width: 390, height: 844 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.getByRole('button', { name: '深色主题', exact: true }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await expect(map.locator('[data-flight]')).toHaveCount(0)
  await expect(map.locator('.static-arrival')).toHaveCSS('stroke', 'rgb(136, 216, 165)')
  await expect(page.getByText('最近抵达 · 第 4 条 · 策略调整 → 任务协调 · 通过', { exact: true })).toBeVisible()
  await item(page, 4).press('Enter')
  const detail = page.getByRole('dialog', { name: '交接依据' })
  await expect(detail.getByText('这条交接未公开具体依据。')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('narrow-reduced-motion-detail.png') })
  await page.keyboard.press('Escape')
  await expect(item(page, 4)).toBeFocused()
  await item(page, 2).press('Space')
  await expect(detail).toContainText('步骤检查 → 推理 · 质疑')
  await expect(detail).toContainText('需检查零根边界')
  await page.keyboard.press('Escape')
  await expect(item(page, 2)).toBeFocused()
})

// Run only with the existing read-only #209 D2 service as the Vite API upstream.
test('D2 saved session opens distinct public submissions on the same path', async ({ page }, testInfo) => {
  test.skip(!process.env.T219_D2_ORIGIN, 'Requires the saved D2 service')
  const sessionId = 'session_6334724f6a476702d1db856f4ad9ce03'
  const jobId = 'run_d81b65537c10122de78607d6274108c9'
  const solves: string[] = []
  page.on('request', request => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/agent/jobs') solves.push(request.url())
  })
  const job = page.waitForResponse(response => new URL(response.url()).pathname === `/api/agent/jobs/${jobId}`)
  await openSession(page, sessionId)
  expect((await job).status()).toBe(200)
  await expect(page.getByText('求解进展 · 真实历史记录', { exact: true })).toBeVisible()
  const submissions = messages(page).getByRole('button', { name: /推理 → 步骤检查 · 送审$/ })
  await expect(submissions).toHaveCount(5, { timeout: 15000 })
  const detail = page.getByRole('dialog', { name: '交接依据' })
  for (const [trigger, order, summary] of [
    [submissions.first(), 3, '等待独立核验：求解线性方程 2a + 1 = 7 得到唯一实数 a = 3'],
    [submissions.last(), 15, '等待独立核验：验证 x = 1 与 x = 2 为方程 x² − 3x + 2 = 0 的全部实数根，无遗漏'],
  ] as const) {
    await trigger.press('Enter')
    await expect(detail).toContainText(`第 ${order} 条 · 推理 → 步骤检查 · 送审`)
    await expect(detail).toContainText(summary)
    await expect(detail).toContainText('这条交接未公开具体依据。')
    await page.screenshot({ path: testInfo.outputPath(`public-handoff-${order}.png`) })
    await page.keyboard.press('Escape')
    await expect(trigger).toBeFocused()
  }
  expect(solves).toEqual([])
})
