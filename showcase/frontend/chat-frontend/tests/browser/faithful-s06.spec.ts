import { expect, test, type Page } from '@playwright/test'

const origin = 'http://127.0.0.1:8091'
async function grant(page: Page) {
  const auth = await (await page.request.get(`${origin}/api/check_auth`)).json()
  const response = await page.request.post(`${origin}/api/reviewer/grant`, {
    headers: { 'X-CSRF-Token': auth.csrf_token }, data: { secret: 'local-browser-fixture' },
  })
  expect(response.status()).toBe(200)
  return { 'X-CSRF-Token': auth.csrf_token, 'Idempotency-Key': crypto.randomUUID() }
}

for (const mode of ['solve', 'teach', 'report']) test(`S06 ${mode} restores one automatic answer without manual generation`, async ({ page }) => {
  let sessionId = ''
  page.on('request', r => { if (r.method() === 'POST' && new URL(r.url()).pathname === '/api/agent/jobs') sessionId = r.postDataJSON().session_id })
  const mutations: string[] = []
  page.on('request', r => { if (r.method() === 'POST' && /\/jobs\/[^/]+\/(solve|teach|report)$/.test(new URL(r.url()).pathname)) mutations.push(r.url()) })
  await page.goto('/dashboard-assets/')
  await page.getByLabel('数学问题').fill(`/${mode} S06 browser ${mode}`)
  await page.getByLabel('数学问题').press('Enter')
  const answer = page.getByRole('region', { name: '最终答复' })
  await expect(answer).toContainText('Fake Agent completed', { timeout: 20000 })
  await expect(page.getByLabel('S06 输出模式')).toHaveCount(0)
  if (mode !== 'solve') await expect(answer).toContainText('所选格式生成失败')
  const text = await answer.locator('.report-content').innerText()
  await page.goto(`/dashboard-assets/session/${sessionId}`)
  await page.reload()
  await expect(answer.locator('.report-content')).toHaveText(text)
  expect(mutations).toEqual([])
})

test('late answer cannot replace the next conversation answer', async ({ page }) => {
  const headers = await grant(page)
  const sessions: string[] = []; const jobs: string[] = []
  for (const problem of ['S06 old A', 'S06 current B']) {
    const session = (await (await page.request.post(`${origin}/api/new_chat`, { headers })).json()).new_session_id
    const response = await page.request.post(`${origin}/api/agent/jobs`, { headers: { ...headers, 'Idempotency-Key': crypto.randomUUID() }, data: { session_id: session, message: problem } })
    expect(response.status()).toBe(202); sessions.push(session); jobs.push((await response.json()).job_id)
  }
  let release!: () => void; let held = false; let delivered = false
  const pending = new Promise<void>(resolve => { release = resolve })
  await page.route(`**/api/agent/jobs/${jobs[0]}/answer`, async route => {
    held = true; await pending
    await route.fulfill({ json: { job_id: jobs[0], status: 'succeeded', mode: 'solve', presentation_status: 'ready', notice: null, answer: 'OLD_A_ANSWER' } }); delivered = true
  })
  await page.route(`**/api/agent/jobs/${jobs[1]}/answer`, route => route.fulfill({ json: { job_id: jobs[1], status: 'succeeded', mode: 'solve', presentation_status: 'ready', notice: null, answer: 'CURRENT_B_ANSWER' } }))
  await page.goto(`/dashboard-assets/session/${sessions[0]}`)
  await expect.poll(() => held).toBe(true)
  await page.locator('.session-main').first().click()
  await expect(page.getByRole('region', { name: '最终答复' })).toContainText('CURRENT_B_ANSWER')
  release(); await expect.poll(() => delivered).toBe(true)
  await expect(page.getByRole('region', { name: '最终答复' })).not.toContainText('OLD_A_ANSWER')
})

async function seedOutput(page: Page, problem: string, mode: string): Promise<{ session: string; job: string }> {
  const headers = await grant(page)
  const response = await page.request.post(`${origin}/__test__/legacy-output`, { headers, data: { problem, mode } })
  expect(response.status()).toBe(200)
  return response.json()
}

test('refreshing a terminal report rechecks a changed presentation source', async ({ page }) => {
  const seeded = await seedOutput(page, 'S06 refreshed source', 'teach')
  let reads = 0
  await page.route(`**/api/agent/jobs/${seeded.job}/outputs/teach`, async route => {
    const response = await route.fetch()
    const body = await response.json()
    if (++reads > 1) {
      body.presentation.status = 'needs_review'
      body.presentation.revalidation_reason = 'source_changed'
    }
    await route.fulfill({ response, json: body })
  })
  await page.goto(`/dashboard-assets/run/${seeded.job}`)
  const output = page.getByLabel('S06 输出模式')
  await expect(output).toHaveAttribute('data-artifact-id', /^presentation:/)
  await page.getByRole('button', { name: '刷新持久报告' }).click()
  await expect(output).toContainText('历史表达需要重新审阅')
})

test('F6 paragraph references open their versioned public evidence without replacing the answer', async ({ page }, testInfo) => {
  const seeded = await seedOutput(page, 'F6 evidence walkthrough', 'teach')
  const formalRef = 'verification:' + 'a'.repeat(64)
  await page.route(`**/api/agent/jobs/${seeded.job}/outputs/teach`, async route => {
    const response = await route.fetch()
    const body = await response.json()
    // Controlled public evidence fixture; backend provenance is covered by API contracts.
    body.presentation.sources = [
      { id: 'graph:v3:p1', kind: 'Proposition', grade: 'llm_reviewed', status: 'current', scope: 'statement', graph_version: 3 },
      { id: 'graph:v3:a1', kind: 'Inference', grade: 'llm_reviewed', status: 'current', scope: 'statement', graph_version: 3 },
      { id: formalRef, kind: 'VerificationRecord', grade: 'L2', status: 'current', scope: 'formal_target', specification_version: 1 },
    ]
    const mathematical = body.presentation.paragraphs.find((item: { kind: string }) => item.kind === 'mathematical')
    mathematical.claim_refs = body.presentation.sources.map((item: { id: string }) => item.id)
    await route.fulfill({ response, json: body })
  })
  await page.goto(`/dashboard-assets/run/${seeded.job}`)
  const output = page.getByLabel('S06 输出模式')
  await expect(output).toHaveAttribute('data-artifact-id', /^presentation:/)
  await page.waitForLoadState('networkidle')
  const original = await output.getByLabel('原答案内容').innerText()
  await output.getByRole('button', { name: '表达内容', exact: true }).click()
  const expression = output.getByLabel('表达内容', { exact: true })
  for (const reference of ['graph:v3:p1', 'graph:v3:a1', formalRef]) {
    const link = expression.getByRole('link', { name: reference, exact: true })
    await expect(link).toBeVisible()
    await link.click()
    const targetText = await link.evaluate(element => {
      const target = decodeURIComponent((element as HTMLAnchorElement).hash.slice(1))
      return document.getElementById(target)?.textContent
    })
    expect(targetText).toContain(reference)
  }
  await expect(output.getByLabel('段落来源')).toContainText('formal_target')
  await expect(output.getByLabel('段落来源')).toContainText('L2')
  await output.screenshot({ path: testInfo.outputPath('f6-desktop.png') })
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await output.screenshot({ path: testInfo.outputPath('f6-mobile.png') })
  await output.getByRole('button', { name: '原答案', exact: true }).click()
  await expect(output.getByLabel('原答案内容')).toHaveText(original)
})
