import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'

const { chromium, expect } = createRequire(new URL('../../chat-frontend/package.json', import.meta.url))('@playwright/test')
const base = new URL(process.env.SHOWCASE_URL ?? 'http://127.0.0.1:8220')
const out = resolve(process.env.SHOWCASE_EVIDENCE_DIR ?? '../../../artifacts/issue-220/browser')
await mkdir(out, { recursive: true })
const browser = await chromium.launch()
const failures = []
const cases = [
  { name: 'desktop-light', viewport: { width: 1280, height: 800 }, orange: 'rgb(153, 71, 0)' },
  { name: 'mobile-dark', viewport: { width: 390, height: 844 }, orange: 'rgb(255, 192, 120)' },
]
try {
  for (const { name, viewport, orange } of cases) {
    const page = await browser.newPage({ viewport, reducedMotion: 'reduce' })
    const requests = [], responses = [], browserErrors = []
    page.on('request', r => requests.push({ method: r.method(), url: r.url() }))
    page.on('response', r => responses.push({ status: r.status(), url: r.url() }))
    page.on('pageerror', e => browserErrors.push(e.message))
    page.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') browserErrors.push(m.text()) })
    const button = name => page.getByRole('button', { name, exact: true })
    const capture = (target, phase) => target.screenshot({ path: resolve(out, `${name}-${phase}.png`) })
    try {
      const auth = page.waitForResponse(r => new URL(r.url()).pathname === '/api/check_auth' && r.ok())
      const dashboard = await page.goto(new URL('/dashboard', base).href)
      assert.equal(dashboard.status(), 200)
      await auth
      await expect(page.getByRole('heading', { name: '从模拟示例开始' })).toBeVisible()
      if (name === 'mobile-dark') await button('切换到深色模式').click()
      await page.clock.install()
      await page.clock.pauseAt(new Date(Date.now() + 1500))
      await button('九角色协作演示 参数四次方程的四根之谜').click()
      await page.getByLabel('输出模式').selectOption('report')
      await expect(page.getByLabel('数学问题')).toHaveValue(/^\/report\s/)
      await button('发送').click()

      const progress = page.getByRole('region', { name: '求解进展' })
      const source = page.locator('.source-label')
      const detail = page.getByRole('region', { name: '决策依据' })
      async function advance(from, to) {
        for (let i = from; i < to; i++) {
          await page.clock.runFor(3250)
          await expect(progress.getByText(`${i + 1} / 11 步完成`, { exact: true })).toBeVisible()
          await expect(source).toHaveText('模拟运行')
        }
      }
      await expect(source).toHaveText('模拟运行')
      await advance(0, 6)
      const challenge = button('质疑 · 步骤校验 → 元策略')
      await expect(challenge).toHaveCSS('color', orange)
      await challenge.click()
      await expect(detail).toContainText('a < −1 或 a > 2')
      await expect(detail).toContainText(/a = −3.*积为 −1.*一正一负.*只有两个实根/)
      await expect(detail).toContainText('修正待发布')
      await capture(detail, 'counterexample')

      await advance(6, 7)
      await expect(detail).toContainText('修正待发布')
      await capture(progress, 'waiting')
      await expect(progress.getByText(/交集为 a > 2/)).toBeHidden()

      await advance(7, 8)
      await expect(detail.getByText('修正待发布')).toBeHidden()
      await expect(detail.getByText(/判别式 > 0、2a > 0、a \+ 2 > 0，交集为 a > 2/)).toBeVisible()
      await expect(detail).toContainText('质疑 · 步骤校验 → 元策略')
      await capture(detail, 'published')

      await advance(8, 11)
      const report = page.getByRole('article', { name: '报告模拟答复' })
      await expect(report.getByText(/两个 y 根互异且均为正/)).toBeVisible()
      const followUp = button('为什么 a = 2 也不行？')
      await followUp.focus()
      await followUp.press('Enter')
      await expect(followUp).toBeFocused()
      await expect(followUp).toHaveAttribute('aria-pressed', 'true')
      const followUpRegion = page.getByRole('region', { name: '步骤追问' })
      await expect(followUpRegion.getByText('修正参数范围', { exact: true })).toBeVisible()
      await expect(followUpRegion.getByText(/\(x² − 2\)² = 0.*x = ±√2 两个不同实根/)).toBeVisible()
      await expect(button('查看推理阶段成果')).toHaveAttribute('data-highlight', 'true')
      await expect(detail).toContainText(/a = 2 时方程为 \(x² − 2\)² = 0/)
      await expect(source).toHaveText('模拟运行')
      await capture(progress, 'boundary')

      assert.ok(responses.some(r => r.status === 200 && /\/dashboard-assets\/workbench\/assets\/index-.*\.js$/.test(r.url)), 'Flask workbench bundle served')
      assert.deepEqual(requests.filter(r => new URL(r.url).origin !== base.origin), [], 'external requests')
      assert.deepEqual(requests.filter(r => !['GET', 'HEAD'].includes(r.method)), [], 'mutating requests, including real solves')
      assert.deepEqual(responses.filter(r => r.status >= 400), [], 'failed HTTP responses')
      assert.deepEqual(browserErrors, [], 'browser errors and warnings')
      console.log(`PASS ${name}: Flask /dashboard, 0 solve requests`)
    } catch (error) {
      failures.push(error)
      console.error(`FAIL ${name}: ${error.message}`)
    } finally {
      await writeFile(resolve(out, `${name}-network.json`), JSON.stringify({ requests, responses, browserErrors }, null, 2))
      await page.close()
    }
  }
} finally {
  await browser.close()
}
if (failures.length) process.exitCode = 1
