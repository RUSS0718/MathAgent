// Acceptance for #223 against a running Faithful service using a fresh data directory.
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { join } from 'node:path'

const { chromium, expect } = createRequire(new URL('../../chat-frontend/package.json', import.meta.url))('@playwright/test')
const base = process.env.SHOWCASE_URL ?? 'http://127.0.0.1:8223'
const evidence = process.env.SHOWCASE_EVIDENCE_DIR
const question = '求这个三角形的面积'
const answer = '底 6 厘米，对应的高 4 厘米'
const area = /(?:^|[^\d.])12(?:\.0+)?\s*(?:平方厘米|厘米\s*[²2]|cm\s*\^?\s*[²2]|square centim(?:eter|etre)s?)/i
const jobsPath = '/api/agent/jobs'
const browser = await chromium.launch()

try {
  if (evidence) await mkdir(evidence, { recursive: true })
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' })
  const errors = []
  const writes = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', request => {
    if (request.method() === 'POST') writes.push(decodeURIComponent(new URL(request.url()).pathname))
  })
  const button = name => page.getByRole('button', { name, exact: true })
  const post = path => page.waitForResponse(response =>
    response.request().method() === 'POST' && decodeURIComponent(new URL(response.url()).pathname) === path)
  const get = async path => {
    const response = await page.request.get(base + path)
    assert.ok(response.ok(), `${path} returned HTTP ${response.status()}`)
    return response.json()
  }
  const capture = async (name, target) => {
    if (evidence) await target.screenshot({ path: join(evidence, `${name}.png`) })
  }

  console.log(`pid=${process.pid} stage=simulation completed=0/5`)
  await page.goto(base + '/dashboard')
  const input = page.getByRole('textbox', { name: '数学问题' })
  const starter = page.locator('.suggestions').getByRole('button', { name: /三角形面积条件补充/ })
  await starter.click()
  await button('发送').click()
  await expect(page.getByText('模拟运行', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '请补充三角形的底和对应的高' })).toBeVisible()
  await page.getByLabel('底（厘米）').fill('6')
  await page.getByLabel('对应的高（厘米）').fill('4')
  await button('补充并继续').click()
  await expect(page.getByRole('article')).toContainText(/12\s*平方厘米/, { timeout: 15_000 })
  await expect(page.getByText('模拟运行', { exact: true })).toBeVisible()
  assert.equal(writes.filter(path => path.startsWith(jobsPath)).length, 0)

  console.log('stage=submit-live completed=1/5')
  const capabilities = await get('/api/capabilities')
  assert.equal(capabilities.jobs?.status, 'available')
  await page.getByRole('navigation', { name: '工作台导航' }).getByRole('button', { name: '新建题目' }).click()
  await input.fill(question)
  const submitted = post(jobsPath)
  await button('发送').click()
  const creation = await submitted
  const submission = creation.request().postDataJSON()
  assert.equal(submission.message, question)
  assert.equal(creation.status(), 202)
  const sessionId = submission.session_id
  assert.ok(sessionId)
  const sessionUrl = `${base}/dashboard/session/${sessionId}`
  await expect(page).toHaveURL(sessionUrl)
  // Navigation can discard the POST body before Chromium returns it to Playwright.
  const { messages } = await get(`/api/load_session?session=${encodeURIComponent(sessionId)}`)
  const submittedQuestion = messages.find(message => message.sender === 'user' && message.text === question)
  const jobId = submittedQuestion?.analysis_job_id
  assert.ok(jobId, 'submitted question is missing its Job in the saved session')
  const jobPath = `${jobsPath}/${jobId}`

  const waitForJob = async (wanted, transient) => {
    let snapshot
    await expect.poll(async () => {
      snapshot = await get(jobPath)
      assert.ok([wanted, ...transient].includes(snapshot.status), `Job ${jobId} stopped in ${snapshot.status}`)
      return snapshot.status
    }, { timeout: 1_100_000, intervals: [1000, 2500, 5000] }).toBe(wanted)
    assert.equal(snapshot.job_id, jobId)
    assert.equal(snapshot.session_id, sessionId)
    return snapshot
  }

  console.log(`stage=await-clarification completed=2/5 job=${jobId} session=${sessionId}`)
  const waiting = await waitForJob('waiting_input', ['queued', 'running'])
  const clarification = waiting.result.faithful.clarification
  assert.equal(clarification.task_id, jobId)
  assert.equal(clarification.status, 'waiting')
  assert.ok(clarification.request_id && clarification.input_version > 0)
  assert.match(clarification.question, /底|高|边长|尺寸|坐标|base|height|side|dimension|length|coordinat/i)
  const panel = page.getByRole('region', { name: '需要补充条件' })
  await expect(panel.getByText(clarification.question, { exact: true })).toBeVisible({ timeout: 15_000 })
  await capture('waiting', panel)

  const clarificationPath = `${jobPath}/clarifications/${clarification.request_id}`
  const receipt = post(clarificationPath)
  await panel.getByRole('textbox', { name: '补充条件' }).fill(answer)
  await button('回答并继续').click()
  const continued = await receipt
  assert.deepEqual(continued.request().postDataJSON(), {
    task_id: jobId, input_version: clarification.input_version, answer,
  })
  assert.equal(continued.status(), 202)
  assert.equal((await continued.json()).job_id, jobId)

  console.log(`stage=await-final-answer completed=3/5 job=${jobId} request=${clarification.request_id}`)
  const final = await waitForJob('succeeded', ['queued', 'running'])
  const result = final.result
  assert.equal(result.execution_mode, 'live')
  assert.equal(result.faithful.clarification.status, 'answered')
  assert.equal(result.faithful.clarification.answer, answer)
  assert.equal(result.faithful.input_version, clarification.input_version + 1)
  const finalRegion = page.getByRole('region', { name: '最终答复' })
  await expect(finalRegion).toContainText(area, { timeout: 30_000 })
  await expect(page.getByText('真实历史记录', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('模拟运行', { exact: true })).toHaveCount(0)
  await expect(page).toHaveURL(sessionUrl)
  await capture('final', finalRegion)

  console.log(`stage=reload completed=4/5 job=${jobId}`)
  const writesBeforeReload = [...writes]
  await page.reload()
  await expect(finalRegion).toContainText(area, { timeout: 30_000 })
  await expect(page).toHaveURL(sessionUrl)
  assert.deepEqual(writes, writesBeforeReload)
  assert.deepEqual(writes.filter(path => path.startsWith(jobsPath)), [jobsPath, clarificationPath])
  assert.deepEqual(errors, [])
  console.log(JSON.stringify({
    status: 'passed', stage: 'finished', completed: '5/5', execution_mode: result.execution_mode,
    job_id: jobId,
    session_id: sessionId, request_id: clarification.request_id,
    input_versions: [clarification.input_version, result.faithful.input_version],
    area_square_cm: 12, simulation_job_writes: 0, refresh_posts: 0, page_errors: errors.length,
  }))
} finally {
  await browser.close()
}
