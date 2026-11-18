import { expect, test, type Page, type APIRequestContext } from '@playwright/test'

const publicOrigin = 'http://127.0.0.1:18090'
const appOrigin = process.env.S09_BROWSER_APP_ORIGIN ?? 'http://127.0.0.1:5176'
const expectedGrade = process.env.S09_BROWSER_FORMAL_GRADE
const expectedAnswer = 'x + x = 2 * x'

type FormalFixture = {
  problem: string
  specification: Record<string, unknown>
  formalPolicy: Record<string, unknown>
}

let formalFixture: Promise<FormalFixture> | null = null

async function loadFormalFixture(request: APIRequestContext): Promise<FormalFixture> {
  formalFixture ??= request.get(`${publicOrigin}/__test__/s09/formal-fixture`).then(async response => {
    expect(response.ok()).toBe(true)
    return response.json() as Promise<FormalFixture>
  })
  return formalFixture
}

async function publicHeaders(page: Page) {
  const response = await page.request.get(`${publicOrigin}/api/check_auth`)
  expect(response.ok()).toBe(true)
  const auth = await response.json()
  return { 'X-CSRF-Token': auth.csrf_token, 'Idempotency-Key': crypto.randomUUID() }
}

async function createFormalJob(page: Page) {
  const fixture = await loadFormalFixture(page.request)
  const headers = await publicHeaders(page)
  const sessionResponse = await page.request.post(`${publicOrigin}/api/new_chat`, { headers })
  expect(sessionResponse.ok()).toBe(true)
  const session = await sessionResponse.json()
  const response = await page.request.post(`${publicOrigin}/api/agent/jobs`, {
    headers,
    data: {
      message: fixture.problem,
      session_id: session.new_session_id,
      solver_mode: 'star_limited',
      problem_spec: fixture.specification,
      formal_policy: fixture.formalPolicy,
    },
  })
  expect(response.status(), await response.text()).toBe(202)
  return (await response.json()).job_id as string
}

async function waitForTerminal(page: Page, jobId: string) {
  await expect.poll(async () => {
    const response = await page.request.get(`${publicOrigin}/api/agent/jobs/${jobId}`)
    if (!response.ok()) return `http_${response.status()}`
    return (await response.json()).status
  }, { timeout: 20_000 }).toMatch(/succeeded|failed|canceled/)
}

for (const viewport of [
  { name: 'desktop', width: 1440, height: 1000 },
  { name: 'mobile', width: 375, height: 812 },
]) {
  test(`real public formal report is read-only on ${viewport.name}`, async ({ page }, testInfo) => {
    const pageErrors: string[] = []
    const consoleErrors: string[] = []
    const posts: string[] = []
    page.on('pageerror', error => pageErrors.push(error.message))
    page.on('console', message => {
      if (message.type() === 'error') consoleErrors.push(message.text())
    })
    page.on('request', request => {
      if (request.method() === 'POST') posts.push(new URL(request.url()).pathname)
    })

    const jobId = await createFormalJob(page)
    await waitForTerminal(page, jobId)
    const job = await (await page.request.get(`${publicOrigin}/api/agent/jobs/${jobId}`)).json()
    const report = await (await page.request.get(`${publicOrigin}/api/agent/jobs/${jobId}/report`)).json()
    const evidence = await (await page.request.get(`${publicOrigin}/api/runs/${jobId}/evidence`)).json()
    expect(job.result.solver.prover_routes).toEqual(report.solver.solver.prover_routes)
    expect(report.report.answer).toContain(expectedAnswer)
    expect(report.solver.solver.formal_verification.status).toBe(expectedGrade ? 'solved' : 'unavailable')
    expect(report.solver.solver.formal_verification.grade).toBe(expectedGrade ?? null)
    expect(evidence.formal_verification).toEqual(report.solver.solver.formal_verification)
    expect(evidence.solver.solver.prover_routes).toEqual(job.result.solver.prover_routes)
    expect(report.report.semantics.whole_review).toBe('accepted')
    expect(report.report.semantics.formal_verification).toBe(expectedGrade ? 'solved' : 'unavailable')
    expect(report.report.prover_routes).toEqual(report.solver.solver.prover_routes)
    expect(report.report.prover_routes).toEqual(expect.arrayContaining([
      expect.objectContaining({ backend_id: 'llm_prover', maximum_grade: 'LLM_REVIEWED' }),
      expect.objectContaining({ backend_id: 'math_tool_backend', maximum_grade: 'L1', grade: 'L1' }),
      expect.objectContaining({ backend_id: 'lean_tactic_prover',
        maximum_grade: expectedGrade === 'L3' ? 'L3' : 'L2' }),
    ]))
    await testInfo.attach('public-job-report-evidence.json', {
      body: JSON.stringify({ job, report, evidence }, null, 2),
      contentType: 'application/json',
    })

    posts.length = 0
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await page.goto(`${appOrigin}/dashboard-assets/run/${jobId}`)

    const formal = page.getByRole('region', { name: '形式验证' })
    const routes = page.getByRole('region', { name: '证明后端路线' })
    await expect(routes).toBeVisible()
    await expect(routes).toContainText('LLM 推导')
    await expect(routes).toContainText('计算工具')
    await expect(routes).toContainText('Lean 后端')
    await expect(routes).toContainText('LLM_REVIEWED')
    await expect(routes).toContainText('L1')
    await expect(routes).toContainText('成本')
    await expect(routes).toContainText('耗时')
    await expect(routes).toContainText('输入 token 未知')
    await expect(formal).toBeVisible()
    await expect(formal).toContainText(expectedGrade === 'L3'
      ? '形式目标与规格对应已独立核验'
      : expectedGrade === 'L2' ? '形式目标已核验；原题对应待独立复核'
        : '形式验证环境不可用；原答案仍保留')
    await expect(formal).toContainText('lean_tactic_prover')
    await expect(formal).toContainText('formal_')
    const answer = page.getByRole('region', { name: '数学报告' })
      .getByText(expectedAnswer, { exact: true })
    await expect(answer).toBeVisible()
    await expect(page.getByLabel('结果语义')).toContainText('LLM 整题审查通过')
    if (!expectedGrade) {
      await expect(formal).not.toContainText('形式目标已核验')
      await expect(formal).not.toContainText('形式目标与规格对应已独立核验')
    }
    expect(posts).toEqual([])

    const postsBeforeReload = [...posts]
    await page.reload()
    await expect(page.getByRole('region', { name: '形式验证' })).toBeVisible()
    await expect(answer).toBeVisible()
    expect(posts).toEqual(postsBeforeReload)

    expect(pageErrors).toEqual([])
    expect(consoleErrors).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({
      path: testInfo.outputPath(`faithful-s09-formal-${viewport.name}.png`),
      fullPage: true,
    })
  })
}
