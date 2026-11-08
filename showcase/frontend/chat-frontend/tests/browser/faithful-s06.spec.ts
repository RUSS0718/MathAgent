import { expect, test } from '@playwright/test'

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
  let releaseFirstTeach!: () => void
  const firstTeachReleased = new Promise<void>((resolve) => { releaseFirstTeach = resolve })
  await page.route('**/api/agent/jobs/*/teach', async (route) => {
    teachRequests += 1
    const response = await route.fetch()
    if (teachRequests === 1) await firstTeachReleased
    await route.fulfill({ response })
  })

  await page.goto('/dashboard-assets/')
  await page.getByLabel('数学问题').fill('/teach S06 browser delayed A')
  await page.getByRole('button', { name: '发送' }).click()
  await expect.poll(() => teachRequests).toBe(1)

  await page.getByLabel('数学问题').fill('/report S06 browser current B')
  await page.getByRole('button', { name: '发送' }).click()
  const output = page.getByLabel('S06 输出模式')
  await expect(output).toContainText('报告', { timeout: 20000 })
  await expect(output).toContainText('S06 browser current B')
  await expect(output).toHaveAttribute('data-source-job-id', /^run_/)
  const currentJobId = await output.getAttribute('data-source-job-id')

  releaseFirstTeach()
  await expect(output).toContainText('报告')
  await expect(output).toContainText('S06 browser current B')
  await expect(output).not.toContainText('S06 browser delayed A')
  await expect(output).toHaveAttribute('data-source-job-id', currentJobId!)
})
