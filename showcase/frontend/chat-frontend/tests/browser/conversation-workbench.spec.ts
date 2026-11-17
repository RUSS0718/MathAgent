import { expect, test } from '@playwright/test'
import { mockWorkspace } from './fixtures'

function frame(id: number, type: string, extra: Record<string, unknown>) {
  return `id: ${id}\nevent: ${type}\ndata: ${JSON.stringify({ type, ...extra })}\n\n`
}

test('default page replaces old chat and submits the actual entered problem with CSRF', async ({ page }) => {
  await mockWorkspace(page, false, stream)
  let submitted = false
  let creations = 0
  await page.route('**/api/load_session?*', route => route.fulfill({ json: { success: true,
    messages: submitted ? [{ sender: 'user', text: '求解 x+1=2', analysis_job_id: 'run-demo' }] : [] } }))
  await page.route('**/api/agent/jobs', async route => {
    creations += 1
    expect(route.request().headers()['x-csrf-token']).toBe('synthetic')
    expect(route.request().postDataJSON().message).toBe('求解 x+1=2')
    submitted = true
    await route.fulfill({ status: 202, json: { success: true, job_id: 'run-demo', status: 'queued' } })
  })
  await page.route('**/api/agent/jobs/run-demo/answer', route => route.fulfill({ json: {
    job_id: 'run-demo', status: 'succeeded', mode: 'solve', presentation_status: 'ready', answer: 'x=1', notice: '模拟答复，未验证。',
  } }))
  await page.goto('/dashboard-assets/')
  await expect(page.getByRole('main')).toBeVisible()
  await expect(page.getByRole('heading', { name: '新建求解 · 输入题干', exact: true })).toBeVisible()
  await page.getByRole('textbox', { name: '数学问题', exact: true }).fill('求解 x+1=2')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await page.locator('.execution-process > summary').click()
  await expect(page.getByRole('region', { name: '对话式执行工作台' })).toBeVisible()
  await expect(page.locator('.workbench-problem')).toContainText('求解 x+1=2')
  await expect(page.getByRole('region', { name: '最终答复' })).toContainText('x=1')
  expect(creations).toBe(1)
  await page.screenshot({ path: '../../../artifacts/workbench-full-page.png', fullPage: true })
})
const progress = { plan_version: 1, attempt_index: 0, steps: [
  { label: '步骤 1', reported: true, current: false, verdict: 'ACCEPT', valid: true },
  { label: '步骤 2', reported: true, current: true, verdict: 'CHALLENGE', valid: false },
] }
const message = { version: 'workbench-v1', thread_id: 'thread-shared', content_status: 'not_published',
  thread_status: 'open', plan_version: 1, attempt_index: 0, step_label: '步骤 2' }
const stream = frame(1, 'solver_progress', { solver_event_type: 'initial_plan_generated', role: 'planner',
  step_id: '步骤 1', solver_revision: 1, solver: { progress }, evidence_kind: 'scripted' })
  + frame(2, 'solver_progress', { solver_event_type: 'step_reviewed', role: 'step_verifier',
    verdict: 'CHALLENGE', workbench: { ...message, message_id: 'message-a', from_role: 'step_verifier', to_role: 'reasoner', kind: 'challenge', summary: '检查边界条件' } })
  + frame(2, 'solver_progress', { solver_event_type: 'step_reviewed', role: 'step_verifier' })
  + frame(3, 'solver_progress', { solver_event_type: 'meta_dispatched', role: 'meta' })
  + frame(4, 'solver_progress', { solver_event_type: 'challenge_replied', role: 'reasoner',
    workbench: { ...message, message_id: 'message-b', from_role: 'reasoner', to_role: 'step_verifier', kind: 'reply', summary: '回复已记录' } })
  + frame(5, 'final_result', { data: { summary: '运行说明不是答案' } })
  + frame(6, 'presentation_artifact_saved', {})

for (const width of [320, 768, 1024, 1440]) {
  test(`ordinary progress filters roles and steps with read-only plan, graph and replay at ${width}px`, async ({ page }) => {
    const posts: string[] = []
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('request', request => { if (request.method() === 'POST') posts.push(new URL(request.url()).pathname) })
    await page.setViewportSize({ width, height: 1000 })
    await mockWorkspace(page, true, stream)
    await page.route('**/api/agent/jobs/run-demo', route => route.fulfill({ json: {
      success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'succeeded', last_event_id: 0,
      result: { execution_mode: 'fake', solver: { state_revision: 1, progress } },
    } }))
    await page.route('**/api/agent/jobs/run-demo/answer', route => route.fulfill({ json: {
      job_id: 'run-demo', status: 'succeeded', mode: 'solve', presentation_status: 'ready', answer: '已保存的模拟答复', notice: '未验证。',
    } }))
    await page.goto('/dashboard-assets/session/session-demo')
    await page.locator('.execution-process > summary').click()
    const workbench = page.getByRole('region', { name: '对话式执行工作台' })
    const entries = workbench.locator('.conversation-events').getByRole('listitem')
    const titles = ['求解计划已形成', '步骤检查已完成', '正在评估调整方案', '已回应步骤疑问', '执行完成，请查看答案和实际检查结论']
    await expect(entries.getByRole('heading')).toHaveText(titles)
    await expect(entries.filter({ hasText: '步骤检查已完成' })).toContainText('检查发现问题，尚未通过。')
    await expect(entries.filter({ hasText: '步骤检查已完成' })).toContainText('步骤检查 → 推理')
    await expect(entries.filter({ hasText: '已回应步骤疑问' })).toContainText('推理 → 步骤检查')
    await workbench.getByText('求解计划与调度详情', { exact: true }).click()
    const plan = workbench.getByRole('complementary', { name: '求解计划' })
    await expect(plan.getByRole('listitem')).toHaveText(['步骤 1步骤检查通过', '步骤 2发现问题'])
    await expect(workbench.getByText('历史回放 · 模拟运行', { exact: true })).toBeVisible()

    await workbench.getByRole('combobox', { name: '角色', exact: true }).selectOption({ label: '推理' })
    await expect(entries.getByRole('heading')).toHaveText(['步骤检查已完成', '已回应步骤疑问'])
    await workbench.getByRole('button', { name: '清除筛选' }).click()
    await expect(entries.getByRole('heading')).toHaveText(titles)
    await workbench.getByRole('combobox', { name: '步骤', exact: true }).selectOption({ label: '步骤 1' })
    await expect(entries.getByRole('heading')).toHaveText(['求解计划已形成'])
    await workbench.getByRole('button', { name: '清除筛选' }).click()
    await expect(entries.getByRole('heading')).toHaveText(titles)

    await workbench.getByRole('button', { name: '完整星图', exact: true }).click()
    const graph = workbench.getByLabel('智能体协作星图', { exact: true })
    await expect(graph).toBeVisible()
    await graph.getByRole('button', { name: /^查看推理 .*阶段成果$/ }).click()
    await workbench.getByRole('button', { name: '关键进展', exact: true }).click()
    await expect(entries.getByRole('heading')).toHaveText(titles)
    await workbench.getByRole('combobox', { name: '角色', exact: true }).selectOption('reasoner')
    await expect(entries.getByRole('heading')).toHaveText(['步骤检查已完成', '已回应步骤疑问'])
    await workbench.getByRole('button', { name: '清除筛选' }).click()
    await expect(entries.getByRole('heading')).toHaveText(titles)
    await workbench.getByText('查看历史回放', { exact: true }).click()
    await workbench.getByRole('slider').fill('4')
    await expect(entries.getByRole('heading')).toHaveText(titles.slice(0, 4))
    await workbench.getByRole('slider').fill('0')
    await expect(entries).toHaveCount(0)
    await expect(workbench.getByText('等待关键进展；请稍候或刷新任务状态。', { exact: true })).toBeVisible()
    await workbench.getByRole('button', { name: '返回任务状态' }).click()
    await expect(entries.getByRole('heading')).toHaveText(titles)
    await workbench.getByRole('button', { name: '深色主题', exact: true }).click()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    await workbench.getByRole('button', { name: '浅色主题', exact: true }).click()
    expect(posts).toEqual([])
    expect(errors).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await workbench.screenshot({ path: `../../../artifacts/workbench-${width}.png` })
  })
}
