import { expect, test } from '@playwright/test'
import { mockWorkspace } from './fixtures'

const source = 'a'.repeat(64)
const result = { source_ref: source, plan_version: 1, attempt_index: 0, stage: 'planning', body_version: 'b'.repeat(64),
  validity: 'current', check: { scope: 'plan_structure', body_version: 'b'.repeat(64) },
  items: [{ label: '步骤 1', title: '平方非负', objective: '对任意实数 x，$(x-1)^2\\geq 0$', depends_on: [] }] }
for (const readingRole of ['planner', 'controller']) {
test(`desktop ${readingRole} saved plan event only prompts until user explicitly updates`, async ({ page }) => {
  await mockWorkspace(page, true)
  await page.addInitScript(() => {
    const original = window.fetch
    window.fetch = async (...args) => {
      if (String(args[0]).includes('/run-demo/events')) {
        return new Response(new ReadableStream({ start(controller) {
          (window as unknown as { pushPlanEvent: (text: string) => void }).pushPlanEvent =
            text => controller.enqueue(new TextEncoder().encode(text))
        } }), { headers: { 'Content-Type': 'text/event-stream' } })
      }
      return original(...args)
    }
  })
  let reads = 0
  const nextSource = 'c'.repeat(64)
  await page.route('**/role-results/*', route => {
    reads++
    const role = new URL(route.request().url()).pathname.split('/').at(-1)
    return route.fulfill({ json: { version: 'role-stage-v1', job_id: 'run-demo', role,
      status: 'succeeded', content_status: 'published', results: [reads === 1 ? result : {
        ...result, source_ref: nextSource, plan_version: 2,
        items: [{ label: '步骤 1', title: '新计划', objective: '新目标', depends_on: [] }],
      }] } })
  })
  await page.goto('/dashboard-assets/session/session-demo')
  await page.waitForFunction(() => 'pushPlanEvent' in window)
  const push = async (id: number, type: string, ref?: string) => {
    const frame = `id: ${id}\nevent: solver_progress\ndata: ${JSON.stringify({ type: 'solver_progress',
      solver_event_type: type, role: 'planner', ...(ref ? { role_stage_source: ref } : {}) })}\n\n`
    await page.evaluate(text => (window as unknown as { pushPlanEvent: (text: string) => void }).pushPlanEvent(text), frame)
  }
  await push(1, 'initial_plan_generated', source)
  await page.locator('.execution-process > summary').click()
  if (readingRole === 'planner') await page.getByRole('button', { name: '查看方案规划阶段成果', exact: true }).click()
  else await page.getByLabel('迷你星图角色成果', { exact: true }).getByRole('button', { name: /^查看任务协调 / }).click()
  const panel = page.getByRole('dialog', { name: readingRole === 'planner' ? '方案规划阶段成果' : '任务协调阶段成果' })
  await expect(panel).toContainText('计划第 1 版')
  const body = await panel.locator('[data-plan-body]').innerText()
  await push(2, 'status_changed', 'd'.repeat(64))
  await push(3, 'plan_replaced') // No saved source means no published update.
  await expect(page.locator('input[type="range"]')).toHaveAttribute('max', '3')
  await expect(panel.getByRole('button', { name: '更新查看', exact: true })).toHaveCount(0)
  await push(4, 'plan_replaced', nextSource)
  await expect(panel.getByRole('button', { name: '更新查看', exact: true })).toBeVisible()
  expect(await panel.locator('[data-plan-body]').innerText()).toBe(body)
  expect(reads).toBe(1)
  await panel.getByRole('button', { name: '更新查看', exact: true }).click()
  await expect(panel).toContainText('计划第 2 版')
  await expect(panel).toContainText('新目标')
  expect(reads).toBe(2)
  await expect(panel.getByRole('button', { name: '更新查看', exact: true })).toHaveCount(0)
})
}

test('desktop dual entry reads the same saved plan, preserves filters and returns keyboard focus', async ({ page }) => {
  const writes: string[] = []
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  page.on('request', r => { if (r.method() !== 'GET') writes.push(r.url()) })
  await mockWorkspace(page, true, `id: 1\nevent: solver_progress\ndata: ${JSON.stringify({ type: 'solver_progress', solver_event_type: 'initial_plan_generated', role: 'planner', role_stage_source: source })}\n\n`)
  await page.route('**/role-results/*', route => route.fulfill({ json: { version: 'role-stage-v1', job_id: 'run-demo', role: 'planner', status: 'succeeded', content_status: 'published', results: [result] } }))
  await page.goto('/dashboard-assets/session/session-demo')
  await page.locator('.execution-process > summary').click()
  const workbench = page.getByRole('region', { name: '对话式执行工作台' })
  const planner = workbench.getByRole('button', { name: '查看方案规划阶段成果', exact: true })
  await planner.focus()
  await page.keyboard.press('Enter')
  const panel = page.getByRole('dialog', { name: '方案规划阶段成果' })
  await expect(panel).toContainText('对任意实数 x')
  await expect(panel.locator('.katex')).toHaveCount(1)
  await page.screenshot({ path: '../../../artifacts/role-stage-200/panel.png' })
  await expect(panel).toContainText('结构校验通过，不代表目标已完成')
  await expect(panel.getByRole('button', { name: '关闭' })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(panel.getByRole('button', { name: '只看该角色' })).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  const first = await panel.locator('[data-plan-body]').innerText()
  await page.keyboard.press('Escape')
  await expect(planner).toBeFocused()
  await workbench.getByRole('button', { name: '完整星图', exact: true }).click()
  const graph = workbench.getByLabel('智能体协作星图', { exact: true })
  const node = graph.getByRole('button', { name: /^查看方案规划 .*阶段成果$/ })
  await node.focus()
  await page.keyboard.press('Space')
  await expect(panel).toBeVisible()
  expect(await panel.locator('[data-plan-body]').innerText()).toBe(first)
  await expect(workbench.getByRole('combobox', { name: '角色', exact: true })).toHaveValue('')
  await panel.getByRole('button', { name: '只看该角色' }).click()
  await expect(workbench.getByRole('combobox', { name: '角色', exact: true })).toHaveValue('planner')
  await expect(node).toBeFocused()
  await page.screenshot({ path: '../../../artifacts/role-stage-200/desktop.png', fullPage: true })
  expect(errors).toEqual([])
  expect(writes.filter(url => !url.endsWith('/api/change_session'))).toEqual([])
})


test('mini coordination entry displays saved arrangements without changing step or role filters', async ({ page }) => {
  await mockWorkspace(page, true, `id: 1\nevent: solver_progress\ndata: ${JSON.stringify({ type: 'solver_progress', solver_event_type: 'initial_plan_generated', role: 'planner', role_stage_source: source })}\n\n`)
  await page.route('**/role-results/*', route => {
    const role = new URL(route.request().url()).pathname.split('/').at(-1)
    return route.fulfill({ json: { version: 'role-stage-v1', job_id: 'run-demo', role, status: 'failed', content_status: 'published', results: [result] } })
  })
  await page.goto('/dashboard-assets/session/session-demo')
  await page.locator('.execution-process > summary').click()
  const workbench = page.getByRole('region', { name: '对话式执行工作台' })
  await workbench.getByRole('combobox', { name: '角色', exact: true }).selectOption('planner')
  const mini = workbench.getByLabel('迷你星图角色成果', { exact: true })
  const node = mini.getByRole('button', { name: /^查看任务协调 / })
  await node.focus()
  await page.keyboard.press('Enter')
  const panel = page.getByRole('dialog', { name: '任务协调阶段成果' })
  await expect(panel).toContainText('协调安排不是数学推导')
  await expect(panel).toContainText('平方非负')
  await expect(workbench.getByRole('combobox', { name: '角色', exact: true })).toHaveValue('planner')
  await expect(workbench.getByRole('combobox', { name: '步骤', exact: true })).toHaveValue('')
  await panel.getByRole('button', { name: '关闭', exact: true }).press('Enter')
  await expect(node).toBeFocused()
})
