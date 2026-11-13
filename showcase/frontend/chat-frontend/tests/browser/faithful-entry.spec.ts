import { expect, test, type Page } from '@playwright/test'
import { mockWorkspace, report } from './fixtures'

test('task revision navigates linked records and ignores late old results', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 375, height: 850 })
  await mockWorkspace(page, true)
  // Production Flask serves the SPA shell here; the isolated Vite server only serves its assets base.
  await page.route('**/dashboard/run/*', async route => route.fulfill({
    response: await page.request.get('/dashboard-assets/'),
  }))
  let changed = false
  let posts = 0
  let releaseOld!: () => void
  const oldEvent = new Promise<void>(resolve => { releaseOld = resolve })
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const snapshot = (old: boolean) => ({
    success: true, job_id: old ? 'run-demo' : 'run-new', session_id: 'session-demo',
    status: old ? changed ? 'canceled' : 'running' : 'succeeded', last_event_id: 0,
    result: { faithful: { input_version: 1, revision_allowed: !old || !changed,
      allowed_actions: old && !changed ? ['cancel'] : [],
      ...(old ? changed ? { revision_to: { task_id: 'run-new' } } : {}
        : { revision_source: { task_id: 'run-demo' } }),
    } },
  })
  await page.route('**/api/load_session?*', route => route.fulfill({ json: { success: true,
    messages: [{ sender: 'user', text: '计算 17×19。', analysis_job_id: 'run-demo' },
      ...(changed ? [{ sender: 'user', text: '计算 2+3。', analysis_job_id: 'run-new' }] : [])],
  } }))
  await page.route('**/api/agent/jobs/run-demo', route => route.fulfill({ json: snapshot(true) }))
  await page.route('**/api/agent/jobs/run-new', route => route.fulfill({ json: snapshot(false) }))
  await page.route('**/api/agent/submissions/*', route => route.fulfill({ json: snapshot(false) }))
  await page.route('**/api/agent/jobs/run-demo/events*', async route => {
    await oldEvent
    await route.fulfill({ contentType: 'text/event-stream',
      body: 'id: 2\nevent: final_result\ndata: {"type":"final_result","status":"succeeded"}\n\n' }).catch(() => {})
  })
  for (const id of ['run-demo', 'run-new']) {
    await page.route(`**/api/agent/jobs/${id}/report`, route => route.fulfill({ json: {
      ...report, evidence_id: id, report: { ...report.report, answer: id === 'run-new' ? '新题答案为 5。' : '旧题结果 999。' },
    } }))
  }
  await page.route('**/api/agent/jobs/run-demo/revisions', async route => {
    posts += 1
    expect(route.request().postDataJSON()).toEqual({ message: '计算 2+3。', input_version: 1 })
    expect(route.request().headers()['x-csrf-token']).toBe('synthetic')
    expect(route.request().headers()['idempotency-key']).toMatch(/^[0-9a-f-]{36}$/)
    changed = true
    await route.fulfill({ status: 202, json: { success: true, job_id: 'run-new', status: 'queued' } })
    releaseOld()
  })
  await page.goto('/dashboard-assets/session/session-demo')
  const revision = page.getByRole('region', { name: '关联任务与改题' })
  await revision.locator('#math-question').fill('计算 2+3。')
  await revision.getByRole('button', { name: '改题并创建新任务', exact: true }).click()
  await expect(page.getByText('新题答案为 5。', { exact: true })).toBeVisible()
  await expect(page.getByText('旧题结果 999。', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('link', { name: '查看原任务', exact: true })).toHaveAttribute('href', '/dashboard/run/run-demo')
  await page.reload()
  await expect(page.getByText('新题答案为 5。', { exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('revision-mobile.png'), fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByRole('link', { name: '查看原任务', exact: true }).click()
  await expect(page.getByRole('link', { name: '查看改题后的任务', exact: true })).toHaveAttribute('href', '/dashboard/run/run-new')
  await page.getByRole('link', { name: '查看改题后的任务', exact: true }).click()
  await expect(page.getByText('新题答案为 5。', { exact: true })).toBeVisible()
  expect(posts).toBe(1)
  expect(errors).toEqual([])
})

const faithful = { enabled: true, ready: true, solver_mode: 'star_reference', input_mode: 'automatic', unavailable_reasons: [] as string[] }
const capabilities = {
  profile: 'showcase', jobs: { enabled: true, status: 'available' }, sse: { enabled: true, status: 'available' },
  verification_mode: ['auto'], files: { upload: { enabled: false } },
  capabilities: { jobs: true, sse: true, verification_mode: ['auto'], file_upload: { enabled: false } },
  solver_modes: [{ solver_mode: 'star_reference', enabled: true, missing_capabilities: [] },
    { solver_mode: 'star_limited', enabled: true, missing_capabilities: [] }],
}
async function setup(page: Page, entry: typeof faithful | undefined) {
  await mockWorkspace(page)
  await page.route('**/api/capabilities', route => route.fulfill({ json: { ...capabilities, faithful: entry } }))
  const requests: Record<string, unknown>[] = []
  await page.route('**/api/agent/jobs', async route => {
    requests.push(route.request().postDataJSON())
    expect(route.request().headers()['x-csrf-token']).toBe('synthetic')
    await route.fulfill({ status: 503, json: { error: '服务暂时不可用' } })
  })
  await page.goto('/dashboard-assets/')
  await expect(page.locator('#math-question')).toBeVisible()
  return requests
}

test('necessary clarification continues the same task and refreshes read-only', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 850 })
  await mockWorkspace(page, true)
  const question = { request_id: 'clarification:run-demo:1', task_id: 'run-demo', input_version: 1,
    question: '三角形底边和对应高是多少？', reason: '数值面积需要实际尺寸。' }
  let answers = 0
  await page.route('**/api/agent/jobs/run-demo', route => route.fulfill({ json: {
    success: true, job_id: 'run-demo', session_id: 'session-demo',
    status: answers ? 'succeeded' : 'waiting_input',
    result: { faithful: { allowed_actions: answers ? [] : ['cancel', 'answer_clarification'],
      clarification: { ...question, status: answers ? 'answered' : 'waiting',
        ...(answers ? { answer: '6 cm 和 4 cm' } : {}) } } },
  } }))
  await page.route('**/api/agent/jobs/run-demo/events**', route => route.fulfill({
    contentType: 'text/event-stream', body: answers
      ? 'id: 2\nevent: final_result\ndata: {"type":"final_result","status":"succeeded"}\n\n'
      : 'id: 1\nevent: interrupt\ndata: {"type":"interrupt","status":"waiting_input"}\n\n',
  }))
  await page.route('**/api/agent/jobs/run-demo/report', route => route.fulfill({ json: {
    ...report, report: { ...report.report, answer: answers ? '面积为 12 cm²。' : '旧错误面积 999' },
  } }))
  await page.route('**/api/agent/jobs/run-demo/clarifications/*', route => {
    answers += 1
    expect(route.request().postDataJSON()).toEqual({ task_id: 'run-demo', input_version: 1, answer: '6 cm 和 4 cm' })
    expect(route.request().headers()['x-csrf-token']).toBe('synthetic')
    return route.fulfill({ status: 202, json: { success: true, job_id: 'run-demo', status: 'queued' } })
  })
  await page.goto('/dashboard-assets/session/session-demo')
  await expect(page.getByText(question.question)).toBeVisible()
  await expect(page.getByRole('button', { name: '恢复执行' })).toHaveCount(0)
  await expect(page.getByText('旧错误面积 999')).toHaveCount(0)
  await page.getByLabel('补充条件', { exact: true }).fill('6 cm 和 4 cm')
  await page.getByRole('button', { name: '回答并继续' }).click()
  await expect(page.getByText('面积为 12 cm²。')).toBeVisible()
  await page.reload()
  await expect(page.getByText('面积为 12 cm²。')).toBeVisible()
  await expect(page.getByText('你的回答：6 cm 和 4 cm')).toBeVisible()
  expect(answers).toBe(1)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('a saved clarification can resume after restart', async ({ page }) => {
  await mockWorkspace(page, true)
  let resumes = 0
  let finished = false
  let releaseEvents!: () => void
  const finish = new Promise<void>(resolve => { releaseEvents = resolve })
  await page.route('**/api/agent/jobs/run-demo', route => route.fulfill({ json: {
    success: true, job_id: 'run-demo', session_id: 'session-demo', status: finished ? 'succeeded' : resumes ? 'queued' : 'failed', last_event_id: finished ? 4 : resumes ? 3 : 2,
    result: { faithful: { allowed_actions: resumes ? [] : ['resume'],
      clarification: { request_id: 'clarification:run-demo:1', task_id: 'run-demo', input_version: 1,
        question: '三角形底边和对应高是多少？', reason: '数值面积需要实际尺寸。',
        status: finished ? 'answered' : 'evaluating', answer: '6 cm 和 4 cm' } } },
  } }))
  await page.route('**/api/agent/jobs/run-demo/events**', async route => {
    await finish
    await route.fulfill({ contentType: 'text/event-stream',
      body: 'id: 4\nevent: final_result\ndata: {"type":"final_result","status":"succeeded"}\n\n' })
  })
  await page.route('**/api/agent/jobs/run-demo/report', route => route.fulfill({ json: {
    ...report, report: { ...report.report, answer: '面积为 12 cm²。' },
  } }))
  await page.route('**/api/agent/jobs/run-demo/resume', route => {
    resumes += 1
    return route.fulfill({ status: 202, json: { success: true, job_id: 'run-demo', status: 'queued' } })
  })
  await page.goto('/dashboard-assets/session/session-demo')
  await expect(page.getByText('你的回答：6 cm 和 4 cm')).toBeVisible()
  await page.getByRole('button', { name: '恢复执行' }).click()
  try {
    await expect.poll(() => resumes).toBe(1)
    await expect(page.getByText('任务执行中', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '恢复执行' })).toHaveCount(0)
  } finally {
    finished = true
    releaseEvents()
  }
  await expect(page.getByText('面积为 12 cm²。')).toBeVisible()
})

test('ready service defaults ordinary submit to Faithful and preserves failed form', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 })
  const requests = await setup(page, faithful)
  await expect(page.getByRole('heading', { name: 'Faithful 自主求解', exact: true })).toBeVisible()
  await expect(page.locator('.faithful-entry')).toContainText('实验性')
  await expect(page.locator('#solver-mode')).not.toBeVisible()
  await page.locator('#math-question').fill('1+1=?')
  await page.getByRole('button', { name: 'Faithful 自主求解', exact: true }).click()
  await expect.poll(() => requests.length).toBe(1)
  expect(requests[0]).toMatchObject({ message: '1+1=?', solver_mode: 'star_reference' })
  await expect(page.locator('#math-question')).toHaveValue('1+1=?')
  await expect(page.locator('.notice')).toBeVisible()
  await expect(page.locator('.notice')).toContainText('服务暂时不可用')
  await expect(page.getByRole('button', { name: 'Faithful 自主求解', exact: true })).toBeEnabled()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('submission state stays visible and prevents duplicate requests', async ({ page }) => {
  await setup(page, faithful)
  let release!: () => void
  const pending = new Promise<void>(resolve => { release = resolve })
  let requests = 0
  await page.route('**/api/agent/jobs', async route => {
    requests += 1
    await pending
    await route.fulfill({ status: 503, json: { error: '服务暂时不可用' } })
  })
  await page.locator('#math-question').fill('1+1=?')
  await page.getByRole('button', { name: 'Faithful 自主求解', exact: true }).click()
  try {
    await expect(page.getByRole('button', { name: '正在提交…', exact: true })).toBeDisabled()
    await expect(page.locator('#math-question')).toBeDisabled()
    await page.locator('form.composer-shell').dispatchEvent('submit')
    await expect.poll(() => requests).toBe(1)
  } finally { release() }
  await expect(page.locator('.notice')).toContainText('服务暂时不可用')
})

test('accepted Faithful submission enters the existing conversation workbench', async ({ page }) => {
  await setup(page, faithful)
  await page.route('**/api/load_session?*', route => route.fulfill({ json: { success: true,
    messages: [{ sender: 'user', text: '1+1=?', analysis_job_id: 'run-demo' }] } }))
  await page.route('**/api/agent/jobs', route => route.fulfill({ status: 202,
    json: { success: true, job_id: 'run-demo', status: 'queued' } }))
  await page.locator('#math-question').fill('1+1=?')
  await page.getByRole('button', { name: 'Faithful 自主求解', exact: true }).click()
  await expect(page.getByRole('region', { name: '对话式执行工作台' })).toBeVisible()
  await expect(page.locator('.workbench-problem')).toContainText('1+1=?')
})

test('capability failure is visible and retry cannot silently submit legacy', async ({ page }) => {
  await setup(page, faithful)
  await page.route('**/api/capabilities', route => route.fulfill({ status: 503, json: { error: '能力检查不可用' } }))
  await page.goto('/dashboard-assets/')
  await expect(page.locator('.notice')).toContainText('能力检查不可用')
  await expect(page.locator('#math-question')).toBeDisabled()
  await page.route('**/api/capabilities', route => route.fulfill({ json: { ...capabilities, faithful } }))
  await page.getByRole('button', { name: '重新加载', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Faithful 自主求解', exact: true })).toBeVisible()
  await expect(page.locator('#math-question')).toBeEnabled()
})

test('enabled but unready blocks button and Enter and shows every missing reason', async ({ page }) => {
  const requests = await setup(page, { ...faithful, ready: false, unavailable_reasons: ['缺少 Python 镜像', '缺少容量证据'] })
  await expect(page.getByRole('alert')).toContainText('缺少 Python 镜像')
  await expect(page.getByRole('alert')).toContainText('缺少容量证据')
  await page.locator('#math-question').fill('保留题干')
  await expect(page.getByRole('button', { name: 'Faithful 自主求解', exact: true })).toBeDisabled()
  await page.locator('#math-question').press('Enter')
  await expect(page.locator('#math-question')).toHaveValue('保留题干')
  expect(requests).toHaveLength(0)
})

test('advanced modes remain explicit and can return to autonomous solving', async ({ page }) => {
  const requests = await setup(page, faithful)
  await page.getByText('高级选项', { exact: true }).click()
  await page.locator('#solver-mode').selectOption('star_limited')
  await page.locator('#math-question').fill('求解 x+1=2')
  await page.getByRole('button', { name: '开始求解', exact: true }).click()
  await expect.poll(() => requests.length).toBe(1)
  expect(requests[0]?.solver_mode).toBe('star_limited')
  await page.getByRole('button', { name: '使用 Faithful 自主求解', exact: true }).click()
  await page.route('**/api/new_chat', route => route.fulfill({ json: { success: true, new_session_id: 'session-resolve' } }))
  await page.getByRole('button', { name: '再次求解', exact: true }).click()
  await expect(page.locator('#math-question')).toHaveValue('求解 x+1=2')
  await page.getByRole('button', { name: 'Faithful 自主求解', exact: true }).click()
  await expect.poll(() => requests.length).toBe(2)
  expect(requests[1]?.solver_mode).toBe('star_reference')
})

for (const entry of [undefined, { ...faithful, enabled: false, ready: false, unavailable_reasons: ['不应显示'] }]) {
  test(`legacy behavior preserved when entry ${entry ? 'disabled' : 'absent'}`, async ({ page }) => {
    const requests = await setup(page, entry)
    await expect(page.locator('#solver-mode')).toBeVisible()
    await expect(page.locator('#solver-mode')).toHaveValue('legacy')
    await expect(page.getByRole('alert')).toHaveCount(0)
    await page.locator('#math-question').fill('1+1=?')
    await page.getByRole('button', { name: '开始求解', exact: true }).click()
    await expect.poll(() => requests.length).toBe(1)
    expect(requests[0]?.solver_mode).toBe('legacy')
  })
}
