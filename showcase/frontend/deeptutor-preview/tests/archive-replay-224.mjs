import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdir } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { join } from 'node:path'

const { chromium, devices, expect } = createRequire(new URL('../../chat-frontend/package.json', import.meta.url))('@playwright/test')
const base = new URL(process.env.SHOWCASE_URL ?? 'http://127.0.0.1:8224').origin
const evidenceDir = process.env.SHOWCASE_EVIDENCE_DIR
// Public record and handoff values from docs/evals/onsite-demo-209-20261118.md.
const originalJob = 'run_d81b65537c10122de78607d6274108c9'
// Opt in when Flask uses the isolated #209 D2 snapshot with the worker disabled.
const checkSavedSession = process.argv.includes('--saved-session')
const originalSession = 'session_6334724f6a476702d1db856f4ad9ce03'
const originalSessionUrl = `${base}/dashboard/session/${originalSession}`
const answerUrl = `${base}/api/agent/jobs/${originalJob}/answer`
const roleUrl = `${base}/api/agent/jobs/${originalJob}/role-results/reasoner`
const stepWait = { timeout: 20_000 }

async function verifySavedSession(page, device) {
  const initialAnswer = page.waitForResponse(answerUrl)
  assert.equal((await page.goto(originalSessionUrl)).status(), 200)
  assert.equal((await initialAnswer).status(), 200)
  const answer = page.getByRole('region', { name: '最终答复' })
  await expect(answer).toBeVisible(stepWait)
  const answerHash = async () => createHash('sha256').update(await answer.innerText()).digest('hex')
  await expect(answer).toContainText('a = 3', stepWait)
  const savedAnswer = await answerHash()
  await page.getByRole('button', { name: '完整星图', exact: true }).click(stepWait)
  await page.getByRole('button', { name: /^查看推理 .*阶段成果$/ }).click(stepWait)

  const dialog = page.getByRole('dialog', { name: '推理阶段成果' })
  const history = dialog.locator('details').filter({ has: page.locator('summary').getByText('历史成果', { exact: true }) })
  const closedHistory = history.and(page.locator('details:not([open])'))
  const contents = dialog.locator('[data-stage-content]')
  const sourceIds = []
  for (const index of [0, 1]) {
    await expect(history).toBeVisible(stepWait)
    if (await closedHistory.count()) await closedHistory.locator('summary').click(stepWait)
    const sourceRead = page.waitForResponse(response => response.url().startsWith(`${roleUrl}?source=`))
    await history.getByRole('button', { name: /步骤提交/ }).nth(index).click(stepWait)
    const response = await sourceRead
    assert.equal(response.status(), 200)
    sourceIds.push(new URL(response.url()).searchParams.get('source'))
    await expect(contents).toBeVisible(stepWait)
    await expect(contents).toContainText(/a\s*=\s*3/, stepWait)
    if (index === 0) {
      const currentRead = page.waitForResponse(roleUrl)
      await dialog.getByRole('button', { name: '查看当前成果' }).click(stepWait)
      assert.equal((await currentRead).status(), 200)
    } else {
      await expect(contents).toContainText(/x²\s*[−-]\s*3x\s*\+\s*2\s*=\s*0/, stepWait)
      if (evidenceDir) await page.screenshot({ path: join(evidenceDir, `${device}-saved-session.png`) })
    }
  }
  assert.notEqual(sourceIds[0], sourceIds[1])
  const reloadedAnswer = page.waitForResponse(answerUrl)
  assert.equal((await page.reload()).status(), 200)
  assert.equal((await reloadedAnswer).status(), 200)
  await expect(page).toHaveURL(originalSessionUrl)
  await expect.poll(answerHash, stepWait).toBe(savedAnswer)
  return { sessionUrl: originalSessionUrl, sourceIds, sameAnswer: true }
}

const evidence = []
const browser = await chromium.launch()

try {
  for (const [device, options] of [
    ['desktop', { viewport: { width: 1280, height: 720 } }],
    ['mobile', devices['Pixel 7']],
  ]) {
    const page = await browser.newPage({ ...options, reducedMotion: 'reduce' })
    try {
      const writes = []
      const errors = []
      page.on('request', request => {
        const url = new URL(request.url())
        if (url.origin === base && !['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
          writes.push(`${request.method()} ${url.pathname}`)
        }
      })
      page.on('pageerror', error => errors.push(error.message))
      page.on('console', message => {
        if (message.type() === 'error') errors.push(message.text())
      })
      const auth = page.waitForResponse(response => response.url() === `${base}/api/check_auth`)
      assert.equal((await page.goto(`${base}/dashboard`)).status(), 200)
      const authenticated = await auth
      assert.equal(authenticated.status(), 200)
      const { permissions } = await authenticated.json()
      assert.ok(permissions.includes('dashboard.access'))
      assert.ok(!permissions.includes('reviewer.access'))

      if (device === 'mobile') await page.getByRole('button', { name: '打开导航' }).click()
      await page.getByRole('navigation', { name: '工作台导航' })
        .getByRole('button', { name: 'D2 协作回放' }).click()
      await expect(page.getByText('D2 真实历史', { exact: false })).toBeVisible()
      const job = page.getByText(`原任务 ${originalJob}`, { exact: true })
      await expect(job).toBeVisible()
      const step = page.getByRole('region', { name: '历史成果' })
      await expect(step.getByText('步骤 1 / 3', { exact: true })).toBeVisible()
      await expect(step.getByText('a = 3', { exact: true })).toBeVisible()
      await page.getByRole('button', { name: '下一步' }).click()
      const substitution = step.getByText(/把第一步的 a = 3 代入 .*得到 x² − 3x \+ 2 = 0/)
      await expect(step.getByText('步骤 2 / 3', { exact: true })).toBeVisible()
      await expect(substitution).toBeVisible()
      const replayUrl = page.url()
      if (evidenceDir) {
        await mkdir(evidenceDir, { recursive: true })
        await page.screenshot({ path: join(evidenceDir, `${device}-handoff.png`), fullPage: true })
      }

      assert.equal((await page.reload()).status(), 200)
      await expect(page).toHaveURL(replayUrl)
      await expect(job).toBeVisible()
      await expect(step.getByText('步骤 2 / 3', { exact: true })).toBeVisible()
      await expect(substitution).toBeVisible()
      await page.getByRole('button', { name: '上一步' }).click()
      await expect(step.getByText('a = 3', { exact: true })).toBeVisible()
      const savedSession = checkSavedSession ? await verifySavedSession(page, device) : undefined
      assert.deepEqual(writes, [])
      assert.deepEqual(errors, [])

      evidence.push({ device, viewport: page.viewportSize(), originalJob, replayUrl, savedSession, writes, errors })
    } finally {
      await page.context().close()
    }
  }
} finally {
  await browser.close()
}
console.log(JSON.stringify(evidence, null, 2))
