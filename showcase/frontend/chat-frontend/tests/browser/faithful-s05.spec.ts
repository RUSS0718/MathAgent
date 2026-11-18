import { expect, test, type Page } from '@playwright/test'

const origin = 'http://127.0.0.1:8091'
const latencyProblem = 'S05 browser event latency'
const longProblem = 'S05 browser long public answer'
const tracebackHistoryProblem = 'S05 browser traceback history: prove 1+1=2'
const replanHistoryProblem = 'S05 browser replan history: prove 1+1=2'
const privateStatement = 'PRIVATE_S05_ROOT_STATEMENT_48e1'
const longAnswer = '公开推导段落。'.repeat(500)

async function create(page: Page, problem: string, withProblemSpec = false): Promise<string> {
  const apiOrigin = withProblemSpec ? 'http://127.0.0.1:8095' : origin
  const auth = await (await page.request.get(`${apiOrigin}/api/check_auth`)).json()
  const headers = { 'X-CSRF-Token': auth.csrf_token, 'Idempotency-Key': crypto.randomUUID() }
  const session = await (await page.request.post(`${apiOrigin}/api/new_chat`, { headers })).json()
  const spec = withProblemSpec ? {
    specification_version: 1,
    original_problem: problem,
    domain: 'integers',
    quantifiers: ['the equality holds'],
    assumptions: ['integer arithmetic'],
    directions: ['prove the statement'],
    output_requirements: ['give the exact value'],
    root_obligations: [{ obligation_id: 'root:s03', obligation_type: 'universal', statement: privateStatement }],
    auxiliary_goals: [],
  } : undefined
  const response = await page.request.post(`${apiOrigin}/api/agent/jobs`, {
    headers,
    data: { message: problem, session_id: session.new_session_id, solver_mode: 'star_limited', ...(spec ? { problem_spec: spec } : {}) },
  })
  const responseBody = await response.text()
  expect(response.status(), responseBody).toBe(202)
  const result = JSON.parse(responseBody) as { job_id: string }
  return result.job_id
}

async function expectTerminal(page: Page, id: string, apiOrigin = origin): Promise<string> {
  let terminalStatus = ''
  await expect.poll(async () => {
    terminalStatus = (await (await page.request.get(`${apiOrigin}/api/agent/jobs/${id}`)).json()).status
    return terminalStatus
  }, { timeout: 20000 }).toMatch(/succeeded|failed|canceled/)
  return terminalStatus
}

async function providerCalls(page: Page, id: string): Promise<number> {
  return (await (await page.request.get('http://127.0.0.1:8092')).json())[id] ?? 0
}

test('lost POST reply replays the same Job identity and request key', async ({ page }) => {
  const keys: string[] = []
  let posts = 0
  let acceptedJobId = ''
  let replay: { job_id: string; existing?: boolean } | null = null
  await page.route('**/api/agent/jobs', async route => {
    if (route.request().method() !== 'POST') return route.continue()
    posts += 1
    keys.push(route.request().headers()['idempotency-key'] ?? '')
    const response = await route.fetch()
    const body = await response.json() as { job_id: string; existing?: boolean }
    expect(response.status(), JSON.stringify(body)).toBe(posts === 1 ? 202 : 200)
    if (posts === 1) {
      acceptedJobId = body.job_id
      await route.abort('failed')
      return
    }
    replay = body
    await route.fulfill({ response, json: body })
  })
  let disconnectFirstStream = true
  let duplicateOnReplay = false
  const streamRequests: Array<{ url: string; lastEventId: string | undefined }> = []
  await page.route('**/api/agent/jobs/*/events*', async route => {
    streamRequests.push({ url: route.request().url(), lastEventId: route.request().headers()['last-event-id'] })
    if (disconnectFirstStream) {
      disconnectFirstStream = false
      await route.abort('failed')
      return
    }
    if (!duplicateOnReplay) return route.continue()
    duplicateOnReplay = false
    const response = await route.fetch()
    const body = await response.text()
    const blocks = body.trim().split(/\r?\n\r?\n/)
    if (blocks.length > 1) blocks.splice(1, 0, blocks[0]!)
    await route.fulfill({ response, body: blocks.join('\n\n') + '\n\n' })
  })

  await page.goto('http://127.0.0.1:5186/dashboard-assets/')
  await page.locator('#solver-mode').selectOption('star_limited')
  await page.getByLabel('数学问题').fill(latencyProblem)
  await page.getByRole('button', { name: '发送' }).click()
  await expect(page.getByRole('status').filter({ hasText: '无法连接服务器' })).toBeVisible()
  await page.getByRole('button', { name: '发送' }).click()
  await expect.poll(() => posts).toBe(2)
  await expect.poll(() => replay?.existing).toBe(true)
  expect(replay?.job_id).toBe(acceptedJobId)
  expect(keys).toHaveLength(2)
  expect(keys[0]).toBeTruthy()
  expect(keys[1]).toBe(keys[0])
  await expectTerminal(page, acceptedJobId)
  expect(await providerCalls(page, acceptedJobId)).toBeGreaterThan(0)
  await expect.poll(() => streamRequests.length).toBeGreaterThanOrEqual(2)
  expect(streamRequests[1]?.lastEventId).toBe('0')
  await expect(page.getByLabel('角色活动')).toContainText('Planner')
  const callsBeforeReplay = await providerCalls(page, acceptedJobId)
  duplicateOnReplay = true
  await page.goto(`http://127.0.0.1:5186/dashboard-assets/run/${acceptedJobId}`)
  await expect(page.locator('[data-event-id][data-event-created-at]').first()).toBeVisible()
  await expect.poll(() => duplicateOnReplay).toBe(false)
  const ids = await page.locator('[data-event-id][data-event-created-at]').evaluateAll(elements => elements.map(element => (element as HTMLElement).dataset.eventId))
  expect(new Set(ids).size).toBe(ids.length)
  await page.getByRole('button', { name: '刷新持久报告' }).click()
  expect(await providerCalls(page, acceptedJobId)).toBe(callsBeforeReplay)
})

test('ProblemSpec progress and timeline recover with measured persisted-event P95', async ({ page }, info) => {
  const id = await create(page, latencyProblem, true)
  await page.goto(`http://127.0.0.1:5187/dashboard-assets/run/${id}`)
  const specOrigin = 'http://127.0.0.1:8095'
  const persistedEventsUrl = `${specOrigin}/__test__/jobs/${id}/persisted-event-times`
  const samples: Array<{
    event_id: number; event: string; workspace_events_created_at_utc: string;
    browser_visible_dom_at_utc: string; latency_ms: number;
  }> = []
  const sampledIds = new Set<number>()
  const samplingDeadline = Date.now() + 20000
  let jobStatus = ''
  const recordVisibleSamples = async (persisted: Array<{ id: number; event: string; created_at: string }>): Promise<void> => {
    for (const event of persisted) {
      if (sampledIds.has(event.id)) continue
      const eventDom = page.locator(`[data-event-id="${event.id}"][data-event-created-at]`).first()
      if (!await eventDom.isVisible().catch(() => false)) continue
      const createdAtInDom = await eventDom.getAttribute('data-event-created-at')
      expect(createdAtInDom).toBe(event.created_at)
      const visibleAt = await page.evaluate(() => new Date().toISOString())
      const latencyMs = Date.parse(visibleAt) - Date.parse(event.created_at)
      expect(Number.isFinite(latencyMs)).toBe(true)
      samples.push({
        event_id: event.id,
        event: event.event,
        workspace_events_created_at_utc: event.created_at,
        browser_visible_dom_at_utc: visibleAt,
        latency_ms: latencyMs,
      })
      sampledIds.add(event.id)
    }
  }
  while (Date.now() < samplingDeadline) {
    const persisted = await (await page.request.get(persistedEventsUrl)).json() as Array<{ id: number; event: string; created_at: string }>
    await recordVisibleSamples(persisted)
    const job = await (await page.request.get(`${specOrigin}/api/agent/jobs/${id}`)).json()
    jobStatus = job.status
    if (['succeeded', 'failed', 'canceled'].includes(jobStatus) && sampledIds.size === persisted.length) break
    await page.waitForTimeout(25)
  }
  expect(jobStatus).toBe('succeeded')
  const terminalPersisted = await (await page.request.get(persistedEventsUrl)).json() as Array<{ id: number; event: string; created_at: string }>
  const expectedRenderedIds = terminalPersisted.map(event => event.id)
  await expect.poll(async () => {
    const renderedIds = await page.locator('[data-event-id][data-event-created-at]').evaluateAll(elements => elements.map(element => Number((element as HTMLElement).dataset.eventId)))
    return [...new Set(renderedIds)].sort((left, right) => left - right)
  }, { timeout: 5000 }).toEqual([...expectedRenderedIds].sort((left, right) => left - right))
  await recordVisibleSamples(terminalPersisted)
  expect(samples.map(sample => sample.event_id).sort((left, right) => left - right)).toEqual([...expectedRenderedIds].sort((left, right) => left - right))
  expect(samples.length).toBe(expectedRenderedIds.length)
  const completedJob = await (await page.request.get(`${specOrigin}/api/agent/jobs/${id}`)).json()
  expect(completedJob.status, JSON.stringify(completedJob)).toBe('succeeded')
  const completedReport = await (await page.request.get(`${specOrigin}/api/agent/jobs/${id}/report`)).json()
  expect(completedReport.solver?.solver?.progress, JSON.stringify(completedReport)).toBeTruthy()
  await expect(page.getByLabel('根义务台账')).toContainText('1 / 1')
  await expect(page.getByLabel('根义务台账')).toContainText('universal · satisfied')
  await expect(page.getByLabel('计划与尝试历史')).toContainText('计划 1 · 尝试 0 · 当前 · 1 步')
  await expect(page.getByLabel('角色活动')).toContainText('Reasoner')
  await expect(page.getByLabel('角色活动')).toContainText('Verifier')
  const proofGraph = page.getByLabel('证明依赖图')
  await expect(proofGraph).toContainText('supported')
  await proofGraph.getByText('查看独立支撑与来源', { exact: true }).first().click()
  await expect(proofGraph).toContainText('accepted')
  await expect(proofGraph).toContainText('llm_reviewed')
  const graphLink = await proofGraph.getByRole('link', { name: /^命题 / }).first().getAttribute('href')
  expect(graphLink).toContain(`proof-${id}-v`)
  await expect(page.locator('[data-event-id][data-event-created-at]').first()).toBeVisible()
  samples.sort((left, right) => left.latency_ms - right.latency_ms)
  expect(samples.length).toBeGreaterThanOrEqual(10)
  const nearestRank = Math.ceil(0.95 * samples.length)
  const p95Ms = samples[nearestRank - 1].latency_ms
  const raw = {
    source: 'SQLite workspace_events.created_at via test-only read endpoint',
    endpoint: `${specOrigin}/__test__/jobs/${id}/persisted-event-times`,
    endpoint_definition: 'select event_id,event_type,created_at from workspace_events where job_id=? order by event_id',
    destination: 'first visible browser DOM frame containing matching data-event-id',
    expected_rendered_event_count: expectedRenderedIds.length,
    expected_rendered_event_ids: expectedRenderedIds,
    sample_count: samples.length,
    nearest_rank_1_based: nearestRank,
    p95_ms: p95Ms,
    local_controlled_provider_only: true,
    provider_live_sla_claimed: false,
    samples,
  }
  const fs = await import('node:fs/promises')
  const rawPath = info.outputPath('persisted-event-dom-latency.json')
  await fs.mkdir(info.outputDir, { recursive: true })
  await fs.writeFile(rawPath, JSON.stringify(raw, null, 2) + '\n')
  expect(p95Ms).toBeLessThanOrEqual(2000)
  expect(await providerCalls(page, id)).toBeGreaterThan(0)
  expect(await page.locator('body').innerText()).not.toContain(privateStatement)
  const callsBeforeRefresh = await providerCalls(page, id)
  await page.reload()
  await expect(page.getByLabel('根义务台账')).toContainText('1 / 1')
  await expect(page.getByLabel('证明依赖图')).toContainText('supported')
  expect(await providerCalls(page, id)).toBe(callsBeforeRefresh)
  await expect(page.locator('[data-event-id][data-event-created-at]').first()).toBeVisible()
  await page.screenshot({ path: info.outputPath('problem-spec-progress.png'), fullPage: true })
})

test('real traceback and replan history remain visible after refresh', async ({ page }, info) => {
  const specOrigin = 'http://127.0.0.1:8095'
  const tracebackJob = await create(page, tracebackHistoryProblem, true)
  const tracebackStatus = await expectTerminal(page, tracebackJob, specOrigin)
  expect(tracebackStatus).toMatch(/^(succeeded|failed)$/)
  const tracebackReport = await (await page.request.get(`${specOrigin}/api/agent/jobs/${tracebackJob}/report`)).json()
  const tracebackHistory = tracebackReport.solver?.solver?.progress?.plan_history
  expect(tracebackHistory, JSON.stringify({ tracebackStatus, tracebackReport })).toEqual(expect.arrayContaining([
    expect.objectContaining({ plan_version: 1, attempt_index: 0, status: 'retried', outcome: 'trace_back' }),
    expect.objectContaining({ plan_version: 1, attempt_index: 1, status: 'current' }),
  ]))
  await page.goto(`http://127.0.0.1:5187/dashboard-assets/run/${tracebackJob}`)
  await expect(page.getByLabel('计划与尝试历史')).toContainText('计划 1 · 尝试 0 · 已回退并重试')
  await expect(page.getByLabel('计划与尝试历史')).toContainText('计划 1 · 尝试 1 · 当前')
  await expect(page.getByRole('button', { name: /^回退与依赖失效/ })).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('计划与尝试历史')).toContainText('计划 1 · 尝试 0 · 已回退并重试')
  await expect(page.getByLabel('计划与尝试历史')).toContainText('计划 1 · 尝试 1 · 当前')
  await expect(page.getByRole('button', { name: /^回退与依赖失效/ })).toBeVisible()

  const replanJob = await create(page, replanHistoryProblem, true)
  const replanStatus = await expectTerminal(page, replanJob, specOrigin)
  const replanReport = await (await page.request.get(`${specOrigin}/api/agent/jobs/${replanJob}/report`)).json()
  expect(replanStatus).toBe('succeeded')
  expect(replanReport.report.answer).toBe('2')
  expect(replanReport.solver?.solver?.progress?.root_obligations?.covered).toBe(1)
  expect(replanReport.solver?.solver?.progress?.plan_history, JSON.stringify(replanReport)).toEqual(expect.arrayContaining([
    expect.objectContaining({ plan_version: 1, attempt_index: 0, status: 'archived', outcome: 'replan' }),
    expect.objectContaining({ plan_version: 2, attempt_index: 1, status: 'current' }),
  ]))
  await page.goto(`http://127.0.0.1:5187/dashboard-assets/run/${replanJob}`)
  await expect(page.getByLabel('计划与尝试历史')).toContainText('计划 1 · 尝试 0 · 已归档')
  await expect(page.getByLabel('计划与尝试历史')).toContainText('计划 2 · 尝试 1 · 当前')
  await expect(page.getByRole('button', { name: /^归档旧计划/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /^执行新计划/ })).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('计划与尝试历史')).toContainText('计划 1 · 尝试 0 · 已归档')
  await expect(page.getByLabel('计划与尝试历史')).toContainText('计划 2 · 尝试 1 · 当前')
  await expect(page.getByRole('button', { name: /^归档旧计划/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /^执行新计划/ })).toBeVisible()
  await page.screenshot({ path: info.outputPath('traceback-replan-history-after-refresh.png'), fullPage: true })
  await expect(page.locator('body')).not.toContainText(privateStatement)
})

test('long public answer stays recoverable after refresh without another solver call', async ({ page }, info) => {
  const id = await create(page, longProblem, true)
  const specOrigin = 'http://127.0.0.1:8095'
  await expectTerminal(page, id, specOrigin)
  const calls = await providerCalls(page, id)
  await page.goto(`http://127.0.0.1:5187/dashboard-assets/run/${id}`)
  const disclosure = page.getByText(/^展开完整答案 · /)
  await expect(disclosure).toBeVisible()
  const longArtifact = page.locator('details.report-long-artifact')
  await expect(longArtifact).not.toHaveAttribute('open')
  await longArtifact.locator('summary').click()
  await expect(longArtifact).toHaveAttribute('open', '')
  await expect(page.locator('[data-public-long-artifact]')).toContainText(longAnswer.slice(0, 100))
  await page.screenshot({ path: info.outputPath('long-answer-expanded.png'), fullPage: true })
  await page.reload()
  await expect(page.getByText(/^展开完整答案 · /)).toBeVisible()
  await expect(page.locator('details.report-long-artifact')).not.toHaveAttribute('open')
  await expect(page.locator('[data-public-long-artifact]')).not.toBeVisible()
  await page.locator('details.report-long-artifact summary').click()
  await expect(page.locator('[data-public-long-artifact]')).toContainText(longAnswer.slice(0, 100))
  expect(await providerCalls(page, id)).toBe(calls)
})

test('switching between persisted Jobs never mixes report or timeline identity', async ({ page }) => {
  const specOrigin = 'http://127.0.0.1:8095'
  const firstJob = await create(page, latencyProblem, true)
  const secondJob = await create(page, longProblem, true)
  await expectTerminal(page, firstJob, specOrigin)
  await expectTerminal(page, secondJob, specOrigin)

  const firstPersisted = await (await page.request.get(`${specOrigin}/__test__/jobs/${firstJob}/persisted-event-times`)).json() as Array<{ id: number }>
  const secondPersisted = await (await page.request.get(`${specOrigin}/__test__/jobs/${secondJob}/persisted-event-times`)).json() as Array<{ id: number }>
  const firstIds = new Set(firstPersisted.map(event => String(event.id)))
  const secondIds = new Set(secondPersisted.map(event => String(event.id)))
  expect([...firstIds].some(id => secondIds.has(id))).toBe(false)

  await page.goto(`http://127.0.0.1:5187/dashboard-assets/run/${firstJob}`)
  await expect(page.getByText(firstJob, { exact: true })).toBeVisible()
  await expect(page.getByLabel('根义务台账')).toContainText('1 / 1')
  await expect(page.locator('details.report-long-artifact')).toHaveCount(0)
  const firstRendered = await page.locator('[data-event-id][data-event-created-at]').evaluateAll(elements => elements.map(element => (element as HTMLElement).dataset.eventId!))
  expect(firstRendered.length).toBeGreaterThan(0)
  expect(firstRendered.every(id => firstIds.has(id))).toBe(true)

  await page.goto(`http://127.0.0.1:5187/dashboard-assets/run/${secondJob}`)
  await expect(page.getByText(secondJob, { exact: true })).toBeVisible()
  await expect(page.getByText(/^展开完整答案 · /)).toBeVisible()
  await expect(page.locator('details.report-long-artifact')).toHaveCount(1)
  const secondRendered = await page.locator('[data-event-id][data-event-created-at]').evaluateAll(elements => elements.map(element => (element as HTMLElement).dataset.eventId!))
  expect(secondRendered.length).toBeGreaterThan(0)
  expect(secondRendered.every(id => secondIds.has(id))).toBe(true)
  expect(secondRendered.some(id => firstIds.has(id))).toBe(false)
})
