import { expect, test, type Page } from '@playwright/test'
import { mockWorkspace } from './fixtures'

// Synthetic saved data exercises presentation only; it is not capability evidence.
const roles = ['任务协调', '问题探索', '方案规划', '推理', '步骤检查', '答案审查', '答案整理', '策略调整', '资料研究']
const duties = ['组织阶段安排与任务派发', '探索题目结构', '安排求解目标', '执行计划步骤', '检查指定步骤',
  '审查指定整题候选', '整理候选答案', '评估处理策略', '查找与题目有关的资料']
const source = 'a'.repeat(64)
const frame = (role: string, ref?: string) => `id: 1\nevent: solver_progress\ndata: ${JSON.stringify({ type: 'solver_progress', solver_event_type: 'step_reported', role, ...(ref ? { role_stage_source: ref } : {}) })}\n\n`
test.beforeEach(async ({ page }) => { await mockWorkspace(page, true, '') })
async function workspace(page: Page, stream = '') {
  if (stream) await page.route(/\/run-demo\/events(?:\?|$)/, route => route.fulfill({ contentType: 'text/event-stream', body: stream }))
  await page.goto('/dashboard-assets/session/session-demo')
  await page.getByRole('button', { name: '关键进展', exact: true }).click()
}
const graph = (page: Page) => page.getByLabel('迷你星图角色成果', { exact: true })
const panel = (page: Page) => page.getByRole('dialog')
test('all nine idle roles open with duties, independent filtering and keyboard focus', async ({ page }) => {
  const writes: string[] = []
  page.on('request', r => { if (r.method() !== 'GET' && !r.url().endsWith('/api/change_session')) writes.push(r.url()) })
  await page.route('**/role-results/*', route => route.fulfill({ json: { version: 'role-stage-v1', job_id: 'run-demo',
    role: new URL(route.request().url()).pathname.split('/').at(-1), status: 'failed', content_status: 'empty', results: [], history: [] } }))
  await workspace(page)
  for (const [index, role] of roles.entries()) {
    const node = graph(page).getByRole('button', { name: new RegExp(`^查看${role} `) })
    await node.focus()
    await page.keyboard.press(index % 2 ? 'Space' : 'Enter')
    await expect(panel(page)).toBeVisible()
    await expect(panel(page).getByRole('button', { name: '关闭', exact: true })).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(panel(page).getByRole('button', { name: '只看该角色' })).toBeFocused()
    await expect(panel(page)).toContainText('职责：')
    await expect(panel(page)).toContainText(duties[index]!)
    await expect(panel(page)).toContainText('未参与')
    if (role !== '任务协调') await expect(panel(page)).not.toContainText('协调安排不是数学推导')
    await expect(page.getByRole('combobox', { name: '角色', exact: true })).toHaveValue('')
    await page.keyboard.press('Escape')
    await expect(node).toBeFocused()
  }
  const removedNode = graph(page).getByRole('button', { name: /^查看推理 / })
  await removedNode.press('Enter')
  await removedNode.evaluate(element => element.remove())
  await page.keyboard.press('Escape')
  await expect(graph(page)).toBeFocused()
  expect(writes).toEqual([])
})

test('legacy event never reads current until explicitly requested, and lost trigger has fallback', async ({ page }) => {
  const reads: string[] = []
  await page.route('**/role-results/*', route => {
    reads.push(route.request().url())
    return route.fulfill({ json: { version: 'role-stage-v1', job_id: 'run-demo', role: 'reasoner', status: 'failed', content_status: new URL(route.request().url()).searchParams.has('source') ? 'unavailable' : 'empty', results: [], history: [] } })
  })
  await workspace(page, frame('reasoner'))
  const trigger = page.getByRole('button', { name: '查看推理阶段成果', exact: true })
  await trigger.press('Enter')
  await expect(panel(page)).toContainText('该条历史成果无法还原')
  expect(reads.every(url => new URL(url).searchParams.has('source'))).toBe(true)
  await panel(page).getByRole('button', { name: '查看当前成果', exact: true }).press('Space')
  await expect(panel(page)).toContainText('尚无已保存成果')
  expect(reads.filter(url => !new URL(url).searchParams.has('source'))).toHaveLength(1)
  await trigger.evaluate(element => element.remove())
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: '关键进展', exact: true })).toBeFocused()
})

const saved = (index = 0) => ({ source_ref: (index + 1).toString(16).repeat(64), plan_version: 1, attempt_index: index,
  stage: 'step_submission', body_version: 'b'.repeat(64), validity: 'current',
  check: { scope: 'step', body_version: 'b'.repeat(64), status: 'unreviewed', label: '步骤候选，未检查' },
  items: [], sections: [{ label: '公式与条件', text: `成果${index + 1}：对任意实数 $x$，$\\sum_{k=1}^{100}(x-k)^2\\geq 0$；仅讨论实数域，取等条件须另行核对。` }] })
const dto = (role = 'reasoner', results = [saved()]) => ({ version: 'role-stage-v1', job_id: 'run-demo', role,
  status: 'failed', content_status: 'published', results, history: [] })

test('step verdict remains readable and bound to its saved source', async ({ page }) => {
  const results = ['accepted', 'rejected', 'unknown'].map((status, index) => ({ ...saved(index),
    stage: 'step_review', check: { ...saved(index).check, scope: 'step_model_review', status,
      label: '步骤模型检查（仅限本步目标）' }, sections: [{ label: '检查对象', text: `目标${index + 1}` }] }))
  await page.route('**/role-results/*', route => route.fulfill({ json: dto('step_verifier', results) }))
  await workspace(page)
  await graph(page).getByRole('button', { name: /^查看步骤检查 / }).click()
  const bodies = panel(page).locator('[data-plan-body]')
  for (const [index, label] of ['通过', '未通过', '结论未知'].entries()) {
    await expect(bodies.nth(index)).toContainText(`检查结论：${label}`)
    await expect(bodies.nth(index)).toContainText(`目标${index + 1}`)
    await expect(bodies.nth(index)).toContainText('仅限本步目标')
    await expect(bodies.nth(index)).toContainText('当前版本有效')
  }
  await page.screenshot({ path: '../../../artifacts/role-stage-final-fix/check-status.png' })
})

test('loading, unpublished, failure and retry stay distinct and never write', async ({ page }) => {
  let answer!: () => void
  let mode = 'delayed'
  const gate = new Promise<void>(resolve => { answer = resolve })
  const reads: string[] = [], writes: string[] = []
  page.on('request', r => { if (r.method() !== 'GET' && !r.url().endsWith('/api/change_session')) writes.push(r.url()) })
  await page.route('**/role-results/*', async route => {
    reads.push(route.request().url())
    if (mode === 'delayed') await gate
    if (mode === 'error') return route.fulfill({ status: 503, json: { code: 'unavailable' } })
    return route.fulfill({ json: { ...dto('reasoner', []), content_status: 'not_published' } })
  })
  await workspace(page, frame('reasoner', source))
  await page.getByRole('button', { name: '查看推理阶段成果', exact: true }).click()
  await expect(panel(page)).toContainText('正在读取已保存成果')
  await expect(panel(page)).not.toContainText('尚无已保存成果')
  answer()
  await expect(panel(page)).toContainText('成果内容未公开')
  await page.keyboard.press('Escape')
  mode = 'error'
  await graph(page).getByRole('button', { name: /^查看推理 / }).press('Space')
  await expect(panel(page)).toContainText('读取失败，最新状态未确认')
  await expect(panel(page)).not.toContainText('尚无已保存成果')
  mode = 'success'
  const beforeRetry = reads.at(-1)
  await panel(page).getByRole('button', { name: '重试读取' }).press('Enter')
  await expect(panel(page)).toContainText('成果内容未公开')
  expect(reads.at(-1)).toBe(beforeRetry)
  expect(writes).toEqual([])
})

test('three complete results initially expanded; more, history and independent filter are keyboard accessible', async ({ page }, testInfo) => {
  const results = Array.from({ length: 4 }, (_, index) => saved(index))
  const old = { ...saved(4), validity: 'invalidated', plan_version: 0 }
  let changed = false
  const latest = { ...saved(6), sections: [{ label: '结论', text: '用户主动读取的最新正文' }] }
  const requests: string[] = []
  await page.route('**/role-results/*', route => {
    const url = new URL(route.request().url()); requests.push(url.search)
    return route.fulfill({ json: { ...dto('reasoner', url.searchParams.get('source') === old.source_ref ? [old] : changed && !url.searchParams.has('source') ? [latest] : results),
      history: [{ source_ref: old.source_ref, plan_version: 0, attempt_index: 4, stage: 'step_submission', body_version: old.body_version, validity: 'invalidated' }] } })
  })
  await workspace(page)
  await page.getByRole('combobox', { name: '角色', exact: true }).selectOption('planner')
  await graph(page).getByRole('button', { name: /^查看推理 / }).press('Enter')
  await expect(panel(page).locator('[data-stage-content]')).toHaveCount(3)
  await expect(panel(page)).toContainText('仅讨论实数域，取等条件须另行核对')
  await expect(panel(page).locator('.katex')).toHaveCount(6)
  await expect(panel(page)).toContainText('步骤候选，未检查')
  await expect(panel(page)).not.toContainText('未参与')
  await expect(page.getByRole('combobox', { name: '角色', exact: true })).toHaveValue('planner')
  await page.keyboard.press('Tab')
  await expect(panel(page).getByRole('button', { name: '更多成果（1 项）' })).toBeFocused()
  await page.keyboard.press('Space')
  await expect(panel(page).locator('[data-stage-content]')).toHaveCount(4)
  await expect(panel(page).getByRole('button', { name: '收起更多成果' })).toBeFocused()
  await expect(panel(page)).not.toContainText('step_submission')
  await expect(panel(page)).not.toContainText(results[0]!.source_ref)
  await page.screenshot({ path: testInfo.outputPath('complete-formulas.png') })
  await panel(page).locator('summary').press('Enter')
  await panel(page).getByRole('button', { name: /计划第 0 版/ }).press('Enter')
  await expect(panel(page)).toContainText('历史成果')
  await expect(panel(page)).toContainText('已失效')
  expect(requests.at(-1)).toBe(`?source=${old.source_ref}`)
  changed = true
  await panel(page).getByRole('button', { name: '查看当前成果', exact: true }).press('Enter')
  await expect(panel(page)).toContainText('用户主动读取的最新正文')
  await expect(panel(page)).not.toContainText('已失效')
  await panel(page).getByRole('button', { name: '只看该角色' }).press('Space')
  await expect(page.getByRole('combobox', { name: '角色', exact: true })).toHaveValue('reasoner')
})

for (const [role, name, savedEvent] of [['reasoner', '推理', 'step_reported'],
  ['researcher', '资料研究', 'reexploration_completed'], ['step_verifier', '步骤检查', 'formal_verification_completed'],
  ['meta', '策略调整', 'plan_archived']] as const) {
test(`${role} saved update and failed authority refresh freeze body, expansion and scroll until explicit update`, async ({ page }) => {
  await page.addInitScript(() => {
    const original = window.fetch
    window.fetch = async (...args) => {
      if (String(args[0]).includes('/run-demo/events')) return new Response(new ReadableStream({ start(controller) {
        (window as unknown as { pushRoleEvent: (text: string) => void }).pushRoleEvent =
          text => controller.enqueue(new TextEncoder().encode(text))
      } }), { headers: { 'Content-Type': 'text/event-stream' } })
      return original(...args)
    }
  })
  let mode = 'initial'
  const next = { ...saved(5), sections: [{ label: '结论', text: '明确更新后的成果' }] }
  await page.route('**/role-results/*', route => {
    if (mode === 'failed') return route.fulfill({ status: 503, json: { code: 'unavailable' } })
    const url = new URL(route.request().url())
    const results = mode === 'initial' ? Array.from({ length: 4 }, (_, i) => saved(i))
      : url.searchParams.has('source') ? [{ ...saved(Number.parseInt(url.searchParams.get('source')![0]!, 16) - 1),
        validity: 'replaced', sections: [{ label: '结论', text: '不得覆盖正在阅读的正文' }] }] : [next]
    return route.fulfill({ json: dto(role, results) })
  })
  await workspace(page)
  await page.waitForFunction(() => 'pushRoleEvent' in window)
  const push = async (id: number, type: string, ref?: string) => {
    await page.evaluate(text => (window as unknown as { pushRoleEvent: (text: string) => void }).pushRoleEvent(text),
      `id: ${id}\nevent: solver_progress\ndata: ${JSON.stringify({ type: 'solver_progress', solver_event_type: type,
        role, ...(ref ? { role_stage_source: ref } : {}) })}\n\n`)
  }
  const node = graph(page).getByRole('button', { name: new RegExp(`^查看${name} `) })
  await node.click()
  await panel(page).getByRole('button', { name: '更多成果（1 项）' }).click()
  const body = await panel(page).locator('[data-stage-content]').allTextContents()
  await panel(page).evaluate(element => { element.scrollTop = 180; element.dispatchEvent(new Event('scroll')) })
  const position = await panel(page).evaluate(element => element.scrollTop)
  expect(position).toBeGreaterThan(0)
  mode = 'changed'
  await push(1, 'status_changed')
  await expect(panel(page)).toContainText('已替换')
  await expect(panel(page).getByRole('button', { name: '更新查看', exact: true })).toHaveCount(0)
  expect(await panel(page).locator('[data-stage-content]').allTextContents()).toEqual(body)
  await push(2, savedEvent, next.source_ref)
  await expect(panel(page).getByRole('button', { name: '更新查看', exact: true })).toBeVisible()
  expect(await panel(page).evaluate(element => element.scrollTop)).toBe(position)
  mode = 'failed'
  await push(3, 'status_changed')
  await expect(page.locator('input[type="range"]')).toHaveAttribute('max', '3')
  await expect(panel(page)).toContainText('最新状态未确认')
  await expect(panel(page)).not.toContainText('当前版本有效')
  expect(await panel(page).locator('[data-stage-content]').allTextContents()).toEqual(body)
  mode = 'changed'
  await panel(page).getByRole('button', { name: '重试读取' }).click()
  await expect(panel(page)).not.toContainText('最新状态未确认')
  expect(await panel(page).locator('[data-stage-content]').allTextContents()).toEqual(body)
  await panel(page).evaluate((element, top) => { element.scrollTop = top; element.dispatchEvent(new Event('scroll')) }, position)
  await page.keyboard.press('Escape')
  await node.press('Enter')
  expect(await panel(page).locator('[data-stage-content]').allTextContents()).toEqual(body)
  expect(await panel(page).evaluate(element => element.scrollTop)).toBe(position)
  await panel(page).getByRole('button', { name: '更新查看', exact: true }).click()
  await expect(panel(page)).toContainText('明确更新后的成果')
  await page.keyboard.press('Escape')
  await push(4, savedEvent, saved(7).source_ref)
  await expect(page.locator('input[type="range"]')).toHaveAttribute('max', '4')
  await node.press('Enter')
  await expect(panel(page).getByRole('button', { name: '更新查看', exact: true })).toBeVisible()
  await expect(panel(page)).toContainText('明确更新后的成果')
})
}

for (const status of ['failed', 'canceled', 'unknown']) {
  test(`${status} job retains saved results and full constellation returns focus`, async ({ page }) => {
    await page.route('**/api/agent/jobs/run-demo', route => route.fulfill({ json: { success: true, job_id: 'run-demo', session_id: 'session-demo', status: status === 'unknown' ? 'running' : status, last_event_id: 0 } }))
    if (status === 'unknown') await page.route(/\/run-demo\/events(?:\?|$)/, route => route.fulfill({ contentType: 'text/event-stream', body: 'id: 1\nevent: solver_progress\ndata: {"type":"solver_progress","solver_event_type":"call_audit","role":"reasoner","call_status":"unknown","solver_call_id":"synthetic-call"}\n\n' }))
    await page.route('**/role-results/*', route => route.fulfill({ json: dto('reasoner') }))
    await page.goto('/dashboard-assets/session/session-demo')
    await page.getByRole('button', { name: '完整星图', exact: true }).click()
    const full = page.getByLabel('智能体协作星图', { exact: true })
    const node = full.getByRole('button', { name: /^查看推理 / })
    await node.press('Space')
    await expect(panel(page)).toContainText('当前版本有效')
    await expect(panel(page)).toContainText('步骤候选，未检查')
    await expect(panel(page)).toContainText('仅讨论实数域')
    if (status === 'unknown') await expect(panel(page)).toContainText('结果未知')
    await panel(page).getByRole('button', { name: '关闭', exact: true }).press('Enter')
    await expect(node).toBeFocused()
  })
}
