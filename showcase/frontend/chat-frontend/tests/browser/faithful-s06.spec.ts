import { expect, test, type Page } from '@playwright/test'

const modes = [
  { command: '/solve', label: '求解' },
  { command: '/teach', label: '教学' },
  { command: '/report', label: '报告' },
]

test('S06 parses Composer output commands and restores each independent artifact', async ({ page }) => {
  const submissions: Array<{ body: Record<string, unknown>; key: string; jobId: string }> = []
  let loseFirstTeachReply = true
  await page.route('**/api/agent/jobs', async (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    const body = route.request().postDataJSON() as Record<string, unknown>
    const key = route.request().headers()['idempotency-key'] ?? ''
    const submission = { body, key, jobId: '' }
    submissions.push(submission)
    const response = await route.fetch()
    const accepted = await response.json() as { job_id?: string }
    submission.jobId = accepted.job_id ?? ''
    if (body.presentation_mode === 'teach' && loseFirstTeachReply) {
      loseFirstTeachReply = false
      await route.abort('failed')
      return
    }
    await route.fulfill({ response })
  })
  await page.goto('/dashboard-assets/')
  const artifactIds: string[] = []

  for (const { command, label } of modes) {
    const problem = `S06 browser ${label}`
    await page.getByLabel('数学问题').fill(`${command} ${problem}`)
    const firstTeachRequestFailed = command === '/teach'
      ? page.waitForEvent('requestfailed', (request) => {
        if (request.method() !== 'POST' || new URL(request.url()).pathname !== '/api/agent/jobs') return false
        return (request.postDataJSON() as Record<string, unknown>).presentation_mode === 'teach'
      })
      : undefined
    await page.getByRole('button', { name: '发送' }).click()
    if (command === '/teach') {
      const failedRequest = await firstTeachRequestFailed!
      expect(failedRequest.failure()).not.toBeNull()
      await expect.poll(() => submissions.filter((item) => item.body.presentation_mode === 'teach' && item.body.message === problem).length).toBe(1)
      const lostTeachSubmission = submissions.find((item) => item.body.presentation_mode === 'teach' && item.body.message === problem)
      expect(lostTeachSubmission?.jobId).toMatch(/^run_/)
      await expect(page.locator('.workspace-notice')).toContainText('无法连接服务器')
      await page.getByRole('button', { name: '发送' }).click()
      await expect.poll(() => submissions.filter((item) => item.body.presentation_mode === 'teach' && item.body.message === problem && item.jobId).length).toBe(2)
      const teachSubmissions = submissions.filter((item) => item.body.presentation_mode === 'teach' && item.body.message === problem)
      expect(teachSubmissions[1]?.key).toBe(teachSubmissions[0]?.key)
      expect(teachSubmissions[1]?.jobId).toBe(teachSubmissions[0]?.jobId)
    }

    await expect.poll(() => submissions.filter((item) => item.body.presentation_mode === command.slice(1) && item.body.message === problem && item.jobId).length).toBeGreaterThan(0)
    const output = page.getByLabel('S06 输出模式')
    await expect(output).toBeVisible({ timeout: 20000 })
    const submitted = submissions.findLast((item) => item.body.presentation_mode === command.slice(1) && item.body.message === problem && item.jobId)
    expect(submitted?.body.message).toBe(problem)
    expect(submitted?.body.presentation_mode).toBe(command.slice(1))
    expect(submitted?.jobId).toMatch(/^run_/)
    await expect(output).toHaveAttribute('data-source-job-id', submitted!.jobId)
    await expect(output).toHaveAttribute('data-presentation-mode', command.slice(1))
    await expect(output).toContainText(label)
    await expect(output).toContainText('Fake Agent completed a deterministic showcase run.')
    await expect(output.getByRole('button', { name: '原答案' })).toBeVisible()
    await expect(output.getByRole('button', { name: '表达内容' })).toBeVisible()
    await expect(output).toContainText('验证状态')
    await expect(output).toHaveAttribute('data-artifact-id', /^presentation:/)
    artifactIds.push((await output.getAttribute('data-artifact-id')) ?? '')
    await output.getByRole('button', { name: '表达内容' }).click()
    await expect(output).toContainText('已验证范围')
    await expect(output).toContainText('当前来源')

    const sessionId = String(submitted?.body.session_id)
    await page.goto(`/dashboard-assets/session/${sessionId}`)
    await page.reload()
    const restored = page.getByLabel('S06 输出模式')
    await expect(restored).toBeVisible({ timeout: 20000 })
    await expect(restored).toHaveAttribute('data-source-job-id', submitted!.jobId)
    await expect(restored).toHaveAttribute('data-presentation-mode', command.slice(1))
    await expect(restored).toContainText(label)
    await expect(restored).toContainText('表达内容')
    await expect(restored).toContainText('已验证范围')
    await expect(restored).toContainText(problem)
    expect(await restored.getAttribute('data-artifact-id')).toBe(artifactIds.at(-1))
  }
  expect(new Set(artifactIds).size).toBe(3)

  await page.getByLabel('数学问题').fill('S06 browser ordinary legacy path')
  await page.getByRole('button', { name: '发送' }).click()
  await expect(page.getByLabel('S06 输出模式')).toHaveCount(0)
  expect(submissions.at(-1)?.body.message).toBe('S06 browser ordinary legacy path')
  expect(submissions.at(-1)?.body).not.toHaveProperty('presentation_mode')
})

test('late presentation responses cannot overwrite a newer Job', async ({ page }) => {
  let teachRequests = 0
  let deliveredTeach = 0
  let releaseFirstTeach!: () => void
  const firstTeachReleased = new Promise<void>((resolve) => { releaseFirstTeach = resolve })
  await page.route('**/api/agent/jobs/*/teach', async (route) => {
    teachRequests += 1
    const response = await route.fetch()
    await firstTeachReleased
    await route.fulfill({ response })
    deliveredTeach += 1
  })

  await page.goto('/dashboard-assets/')
  await page.getByLabel('数学问题').fill('/teach S06 browser delayed A')
  await page.getByRole('button', { name: '发送' }).click()
  await expect.poll(() => teachRequests > 0).toBe(true)

  await page.getByLabel('数学问题').fill('/report S06 browser current B')
  await page.getByRole('button', { name: '发送' }).click()
  const output = page.getByLabel('S06 输出模式')
  await expect(output).toContainText('报告', { timeout: 20000 })
  await expect(output).toContainText('S06 browser current B')
  await expect(output).toHaveAttribute('data-source-job-id', /^run_/)
  const currentJobId = await output.getAttribute('data-source-job-id')

  const heldRequests = teachRequests
  releaseFirstTeach()
  await expect.poll(() => deliveredTeach >= heldRequests).toBe(true)
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => resolve())))
  await expect(output).toContainText('报告')
  await expect(output).toContainText('S06 browser current B')
  await expect(output).not.toContainText('S06 browser delayed A')
  await expect(output).toHaveAttribute('data-source-job-id', currentJobId!)
})

async function seedOutput(page: Page, problem: string, mode: string): Promise<{ session: string; job: string }> {
  const origin = 'http://127.0.0.1:8091'
  const auth = await (await page.request.get(`${origin}/api/check_auth`)).json()
  const headers = { 'X-CSRF-Token': auth.csrf_token, 'Idempotency-Key': crypto.randomUUID() }
  const session = (await (await page.request.post(`${origin}/api/new_chat`, { headers })).json()).new_session_id as string
  const response = await page.request.post(`${origin}/api/agent/jobs`, { headers,
    data: { session_id: session, message: problem, presentation_mode: mode } })
  expect(response.status()).toBe(202)
  const job = (await response.json()).job_id as string
  await expect.poll(async () => (await (await page.request.get(`${origin}/api/agent/jobs/${job}`)).json()).status).toBe('succeeded')
  return { session, job }
}

test('late report cannot become another Jobs original-answer fallback', async ({ page }) => {
  const first = await seedOutput(page, 'S06 old report A', 'teach')
  let held = false
  let delivered = false
  let aReads = 0
  let bReads = 0
  let release!: () => void
  let releaseB!: () => void
  const released = new Promise<void>(resolve => { release = resolve })
  const bReleased = new Promise<void>(resolve => { releaseB = resolve })
  await page.route('**/api/agent/jobs/*/report', async route => {
    if (route.request().method() === 'POST') return route.fulfill({ status: 503, body: '{}' })
    const response = await route.fetch()
    const body = await response.json()
    const isA = route.request().url().includes(first.job)
    if (isA) {
      body.report.answer = 'OLD_A_ANSWER'
      if (++aReads > 1) { held = true; await released }
    } else {
      body.report.answer = 'CURRENT_B_ANSWER'
      if (++bReads > 1) await bReleased
    }
    await route.fulfill({ response, json: body })
    if (isA && aReads > 1) delivered = true
  })
  await page.goto(`/dashboard-assets/session/${first.session}`)
  await expect.poll(() => held).toBe(true)
  await page.getByLabel('数学问题').fill('/report S06 current report B')
  await page.getByRole('button', { name: '发送' }).click()
  const output = page.getByLabel('S06 输出模式')
  await expect(output).toContainText('S06 current report B')
  await expect(output).toContainText('CURRENT_B_ANSWER')
  release()
  try {
    await expect.poll(() => delivered).toBe(true)
    await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => resolve())))
    await expect(output).not.toContainText('OLD_A_ANSWER')
    await expect(output).toContainText('CURRENT_B_ANSWER')
  } finally { releaseB() }
})

test('refreshing a terminal report rechecks a changed presentation source', async ({ page }) => {
  const seeded = await seedOutput(page, 'S06 refreshed source', 'teach')
  let reads = 0
  await page.route(`**/api/agent/jobs/${seeded.job}/teach`, async route => {
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
