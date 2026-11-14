import { expect, test } from '@playwright/test'
import { mockWorkspace } from './fixtures'

for (const width of [375, 1440]) {
  test(`Faithful phase and allowed controls, keyboard at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 })
    await mockWorkspace(page, true)
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    let phase = 'converging'
    let actions: string[] = []
    let pauses = 0
    await page.route('**/api/agent/jobs/run-demo', route => route.fulfill({ json: {
      success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'waiting_input', last_event_id: 0,
      result: { faithful: { phase, allowed_actions: actions } },
    } }))
    await page.route('**/api/agent/jobs/run-demo/events**', route => route.fulfill({ contentType: 'text/event-stream', body: '' }))
    await page.route('**/api/agent/jobs/run-demo/interventions/pause', route => {
      pauses++; phase = 'pause_requested'; actions = []
      return route.fulfill({ json: { success: true, status: 'pause_requested' } })
    })
    await page.goto('/dashboard-assets/session/session-demo')
    const status = page.getByRole('region', { name: 'Faithful 任务状态' })
    await expect(status).toContainText('正在收敛')
    await expect(page.getByRole('button', { name: '恢复执行', exact: true })).toHaveCount(0)
    for (const [next, label] of [['paused', '已暂停'], ['unknown', '结果未知'], ['budget_exhausted', '预算耗尽，任务未完成'], ['failed', '执行失败'], ['incomplete', '任务未完成'], ['completed', '任务完成']]) {
      phase = next!; await page.reload(); await expect(status).toContainText(label!)
    }
    phase = 'running'; actions = ['pause']; await page.reload()
    const pause = status.getByRole('button', { name: '请求安全暂停' })
    await pause.focus(); await page.keyboard.press('Enter')
    await expect(status).toContainText('已请求暂停')
    await expect(pause).toHaveCount(0)
    expect(pauses).toBe(1)
    phase = 'paused'; actions = ['resume']; await page.reload()
    await expect(status.getByRole('button', { name: '恢复执行' })).toHaveCount(0)
    await expect(status).toContainText('请到运行详情使用父 Run 专用恢复控制')
    phase = 'waiting_input'; await page.reload()
    const resume = status.getByRole('button', { name: '恢复执行' })
    await expect(resume).toBeVisible(); await resume.focus(); await expect(resume).toBeFocused()
    await expect(page.getByRole('link', { name: '运行详情', exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath(`faithful-${width}.png`), fullPage: true })
    expect(errors).toEqual([])
  })
}

test('paused parent resumes only with dedicated backend admission and endpoint', async ({ page }) => {
  await mockWorkspace(page, true)
  let actions = ['resume_intervention']
  let dedicatedCalls = 0
  let genericCalls = 0
  await page.route('**/api/agent/jobs/run-demo', route => route.fulfill({ json: {
    success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'waiting_input', last_event_id: 0,
    result: { faithful: { phase: 'paused', allowed_actions: actions } },
  } }))
  await page.route('**/api/agent/jobs/run-demo/events**', route => route.fulfill({ contentType: 'text/event-stream', body: '' }))
  await page.route('**/api/agent/jobs/run-demo/interventions', route => route.fulfill({ json: { success: true, interventions: {
    job_id: 'run-demo', status: 'paused', checkpoint_revision: 12,
    failure_sources: [], root_obligations: [], current_method_id: 'direct', hypotheses: [], actions: [], pairs: [], effects: [],
  } } }))
  await page.route('**/api/agent/jobs/run-demo/interventions/resume', route => {
    dedicatedCalls++
    expect(route.request().method()).toBe('POST')
    expect(route.request().headers()['idempotency-key']).toBeTruthy()
    return route.fulfill({ json: { success: true, job_id: 'run-demo', status: 'queued' } })
  })
  await page.route('**/api/agent/jobs/run-demo/resume', route => {
    genericCalls++
    return route.fulfill({ json: { success: true, status: 'queued' } })
  })
  await page.goto('/dashboard-assets/run/run-demo')
  const section = page.getByRole('region', { name: '同源干预实验' })
  const resume = section.getByRole('button', { name: '显式恢复父 Run' })
  await expect(resume).toBeVisible()
  await resume.focus(); await page.keyboard.press('Enter')
  await expect.poll(() => dedicatedCalls).toBe(1)
  expect(genericCalls).toBe(0)
  actions = ['resume']; await page.reload()
  await expect(section.getByText('当前没有已预留的同源配对。')).toBeVisible()
  await expect(resume).toHaveCount(0)
  actions = []; await page.reload()
  await expect(section.getByText('当前没有已预留的同源配对。')).toBeVisible()
  await expect(resume).toHaveCount(0)
})

test('Faithful recovery obeys backend actions even with expired deadline and unknown calls', async ({ page }) => {
  await mockWorkspace(page, true)
  let actions: string[] = []
  let faithful = true
  let safe = false
  let posts = 0
  await page.route('**/api/agent/jobs/run-demo', route => route.fulfill({ json: {
    success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'failed', last_event_id: 0,
    result: faithful ? { faithful: { phase: 'unknown', allowed_actions: actions } } : {},
  } }))
  await page.route('**/api/agent/jobs/run-demo/events**', route => route.fulfill({ contentType: 'text/event-stream', body: '' }))
  await page.route('**/api/agent/jobs/run-demo/report', async route => {
    const { report } = await import('./fixtures')
    await route.fulfill({ json: { ...report,
      report: { ...report.report, budget: { deadline_at: 0 } },
      solver: { solver_mode: 'star_limited', evidence_kind: 'fault_injection', missing_capabilities: [],
        solver: { run_id: 'run-demo', state_revision: 5, phase: 'EXPLORE', status: 'interrupted',
          recovery: { status: safe ? 'safe' : 'needs_review', unknown_calls: safe ? [] : [{ call_id: 'unknown-call', role: 'explore', status: 'unknown_outcome' }], retries: [] } } },
    } })
  })
  await page.route('**/api/agent/jobs/run-demo/resume', route => {
    posts++; return route.fulfill({ json: { success: true, status: 'queued' } })
  })
  await page.goto('/dashboard-assets/run/run-demo')
  const section = page.getByRole('region', { name: '安全续算' })
  const retry = page.getByRole('button', { name: '明确选择：用新身份重试' })
  const resume = page.getByRole('button', { name: '继续同一任务', exact: true })
  await expect(section).toContainText('旧请求预留')
  await expect(retry).toHaveCount(0)
  actions = ['retry_unknown_call']; await page.reload(); await expect(retry).toBeVisible()
  actions = []; safe = true; await page.reload()
  await expect(section).toContainText('沿用同一任务')
  await expect(resume).toHaveCount(0)
  actions = ['resume']; await page.reload(); await expect(resume).toBeVisible()
  faithful = false; actions = []; await page.reload(); await expect(resume).toBeVisible()
  safe = false; await page.reload(); await expect(retry).toBeVisible()
  expect(posts).toBe(0)
})
