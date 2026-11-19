import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const { chromium, expect } = createRequire(new URL('../../chat-frontend/package.json', import.meta.url))('@playwright/test')
const base = 'http://127.0.0.1:8221'
const [directory, ...savedSessionIds] = process.argv.slice(2)
const output = resolve(directory ?? 'artifacts/decision-evidence-221/browser')
const readback = savedSessionIds.length > 0
assert.ok(!readback || (savedSessionIds.length === 2 && new Set(savedSessionIds).size === 2
  && savedSessionIds.every(id => /^session_[a-f0-9]+$/.test(id))), 'Supply two distinct saved session IDs in input order')
const png = fileURLToPath(new URL('../public/examples/linear-equation.png', import.meta.url))
const sha256 = createHash('sha256').update(await readFile(png)).digest('hex')
assert.equal(sha256, 'e77b5a680ae7b4e4db7724aa215cbdb4577b33d1c2bee4277663b23c69604939')
const cases = [
  { name: 'image-only', message: '', modality: 'image' },
  { name: 'image-with-text', message: '请手算，并把结果代回原方程检验。', modality: 'text_image' },
]
const evidence = { startedAt: new Date().toISOString(), dashboard: `${base}/dashboard`, sha256, readback, cases: [] }
const evidencePath = resolve(output, 'evidence.json')
await mkdir(output, { recursive: true })
await writeFile(evidencePath, JSON.stringify(evidence), { flag: 'wx' })
const checkpoint = () => writeFile(evidencePath, JSON.stringify(evidence, null, 2) + '\n')
const isPost = (request, path) => request.method() === 'POST' && new URL(request.url()).pathname === path
const hasSolution = text => /[x𝑥]=4(?!\d|\.\d)/.test(
  text.replace(/\\(?:boxed|text|mathrm|mathbf)\s*\{/g, '{').replace(/[{}\s\u200b-\u200f]/g, ''),
)

async function readJson(page, path) {
  const response = await page.request.get(base + path)
  assert.equal(response.status(), 200, path)
  return response.json()
}

async function submit(page, test, row) {
  assert.equal((await page.goto(evidence.dashboard)).status(), 200)
  const capabilities = await readJson(page, '/api/capabilities')
  assert.equal(capabilities.files.upload.enabled, true)
  await page.getByRole('button', { name: '题图求解', exact: true }).click()
  await page.getByLabel('选择 PNG 题图').setInputFiles(png)
  await expect(page.getByAltText('待提交的题图')).toBeVisible()
  const requirement = page.getByLabel('补充要求（可选）')
  if (test.message) await requirement.fill(test.message)
  await expect(requirement).toHaveValue(test.message)
  row.phase = 'submit'
  await checkpoint()
  const [upload, submission] = await Promise.all([
    page.waitForResponse(response => isPost(response.request(), '/api/upload_file')),
    page.waitForResponse(response => isPost(response.request(), '/api/agent/jobs')),
    page.getByRole('button', { name: '发送题图', exact: true }).click(),
  ])
  row.uploadHttp = upload.status()
  row.submitHttp = submission.status()
  assert.equal(row.uploadHttp, 201)
  assert.equal(row.submitHttp, 202)
  // The Dashboard navigates immediately after the 202. Read the Job from the saved session.
  const payload = submission.request().postDataJSON()
  assert.ok(payload.session_id && payload.input_user_file_id)
  assert.equal(payload.message, test.message)
  row.sessionId = payload.session_id
  return payload.input_user_file_id
}

async function readSessionJob(page, row, test) {
  const session = await readJson(page, `/api/load_session?session=${encodeURIComponent(row.sessionId)}`)
  const messages = session.messages.filter(message => message.sender === 'user')
  assert.equal(messages.length, 1)
  assert.equal(messages[0].text, test.message)
  assert.ok(messages[0].analysis_job_id)
  const jobIds = [...new Set(session.messages.map(message => message.analysis_job_id).filter(Boolean))]
  assert.deepEqual(jobIds, [messages[0].analysis_job_id])
  return jobIds[0]
}

const browser = await chromium.launch()
try {
  for (const [index, test] of cases.entries()) {
    const row = { name: test.name, phase: 'dashboard', uploads: 0, solvePosts: 0, pageErrors: 0 }
    evidence.cases.push(row)
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, reducedMotion: 'reduce' })
    page.on('pageerror', () => row.pageErrors++)
    page.on('request', request => {
      if (isPost(request, '/api/upload_file')) row.uploads++
      if (isPost(request, '/api/agent/jobs')) row.solvePosts++
    })
    try {
      const submittedFileId = readback ? undefined : await submit(page, test, row)
      if (readback) row.sessionId = savedSessionIds[index]
      const sessionUrl = `${base}/dashboard/session/${row.sessionId}`
      if (readback) assert.equal((await page.goto(sessionUrl)).status(), 200)
      await expect(page).toHaveURL(sessionUrl)
      row.jobId = await readSessionJob(page, row, test)
      row.phase = 'verify-job'
      await checkpoint()

      const jobPath = `/api/agent/jobs/${row.jobId}`
      let job
      await expect.poll(async () => {
        job = await readJson(page, jobPath)
        return job.status
      }, { timeout: 1_130_000, intervals: [1_000, 3_000, 5_000] }).not.toMatch(/^(queued|running)$/)
      row.status = job.status
      const intake = job.result?.input_intake
      row.intake = { status: intake?.status, modality: intake?.modality, problemType: intake?.problem_type }
      row.executionMode = job.result?.execution_mode
      assert.equal(job.job_id, row.jobId)
      assert.equal(job.session_id, row.sessionId)
      assert.ok(job.input_user_file_id)
      if (submittedFileId) assert.equal(job.input_user_file_id, submittedFileId)
      const files = await readJson(page, '/api/files')
      assert.equal(files.find(file => file.file_id === job.input_user_file_id)?.sha256, sha256)
      row.imageSha256 = sha256
      assert.equal(row.executionMode, 'live')
      assert.equal(row.status, 'succeeded')
      assert.equal(intake?.status, 'ready')
      assert.equal(intake?.modality, test.modality)
      assert.equal(intake?.problem_type, 'equation')
      await expect(page.getByText('已读取题图。', { exact: true })).toBeVisible()
      const displayed = page.getByRole('region', { name: '最终答复' }).locator('.report-content')
      await expect(displayed).toBeVisible({ timeout: 20_000 })
      assert.ok(hasSolution(await displayed.innerText()), 'Dashboard final answer must show x = 4')
      const answer = await readJson(page, `${jobPath}/answer`)
      assert.equal(answer.job_id, row.jobId)
      assert.ok(hasSolution(answer.answer), 'The same Job answer must contain x = 4')
      row.answer = 'x = 4'
      await page.screenshot({ path: resolve(output, `${test.name}.png`) })

      await page.reload()
      await expect(page).toHaveURL(sessionUrl)
      await expect(displayed).toBeVisible({ timeout: 20_000 })
      assert.ok(hasSolution(await displayed.innerText()), 'Refreshed Dashboard must show x = 4')
      row.reloadJobId = await readSessionJob(page, row, test)
      assert.equal(row.reloadJobId, row.jobId)
      assert.equal(row.solvePosts, readback ? 0 : 1)
      assert.equal(row.uploads, readback ? 0 : 1)
      assert.equal(row.pageErrors, 0)
      row.phase = 'passed'
    } catch (error) {
      row.failedAt = row.phase
      row.phase = 'failed'
      console.error(test.name, error instanceof Error ? error.message : 'Browser check failed')
    } finally {
      row.finishedAt = new Date().toISOString()
      await page.context().close()
      await checkpoint()
    }
  }
  evidence.finishedAt = new Date().toISOString()
  evidence.solvePosts = evidence.cases.reduce((total, row) => total + row.solvePosts, 0)
  evidence.passed = evidence.solvePosts === (readback ? 0 : 2) && evidence.cases.every(row => row.phase === 'passed')
    && new Set(evidence.cases.map(row => row.jobId)).size === 2
    && new Set(evidence.cases.map(row => row.sessionId)).size === 2
  await checkpoint()
  assert.ok(evidence.passed, 'Both inputs must have distinct successful Jobs and sessions')
} finally {
  await browser.close()
}
