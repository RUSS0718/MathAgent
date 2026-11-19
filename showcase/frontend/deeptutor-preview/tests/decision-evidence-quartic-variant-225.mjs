import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const { chromium, expect } = createRequire(new URL('../../chat-frontend/package.json', import.meta.url))('@playwright/test')
const dashboard = new URL(process.argv[2] ?? 'http://127.0.0.1:8225/dashboard')
const evidence = new URL('../../../../artifacts/issue225/browser/', import.meta.url)
const original = {
  title: '参数四次方程的四根之谜',
  question: '当 a 取何值时，方程 x⁴ − 2ax² + a + 2 = 0 有四个不同实根？若四根从小到大成等差数列，再求 a。',
}
const variant = {
  title: '变式 · 恰有两个不同实根',
  question: '当 a 取何值时，方程 x⁴ − 2ax² + a + 2 = 0 恰有两个不同实根？',
}
const variantAnswer = String.raw`a<-2\quad\text{或}\quad a=2`
const button = (scope, name) => scope.getByRole('button', { name, exact: true })

await mkdir(evidence, { recursive: true })
const browser = await chromium.launch()
try {
  for (const width of [1280, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 844 }, reducedMotion: 'reduce' })
    const writes = []
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
    page.on('request', request => {
      const url = new URL(request.url())
      if (url.origin === dashboard.origin && url.pathname.startsWith('/api/') && !['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
        writes.push(`${request.method()} ${url.pathname}`)
      }
    })

    const response = await page.goto(dashboard.href)
    assert.equal(response.status(), 200)
    assert.match(response.headers().server, /Werkzeug/)
    assert.match(await response.text(), /\/dashboard-assets\/workbench\//)
    await page.clock.install()
    const main = page.getByRole('main')
    const question = main.locator('.question')
    const reports = main.getByRole('article')
    const report = main.getByRole('article', { name: '报告模拟答复', exact: true })
    const result = report.locator('.result .katex')
    const formula = result.locator('annotation')

    async function expectReport(task, answer) {
      await expect(question).toHaveText(task.question)
      await expect(reports).toHaveCount(1)
      await expect(report.getByRole('heading', { name: `求解报告 · ${task.title}`, exact: true })).toBeVisible()
      await expect(result).toBeVisible()
      await expect(formula).toHaveText(answer)
    }

    async function expectCurrentTask(current, other) {
      if (width === 390) await button(main, '打开导航').click()
      const nav = page.getByRole('navigation', { name: '工作台导航', exact: true })
      const currentRow = button(nav, `${current.title} · 报告`)
      const otherRow = button(nav, `${other.title} · 报告`)
      await expect(currentRow).toHaveCount(1)
      await expect(otherRow).toHaveCount(1)
      await expect(currentRow).toBeVisible()
      await expect(otherRow).toBeVisible()
      await expect(currentRow).toHaveAttribute('aria-current', 'page')
      await expect(otherRow).not.toHaveAttribute('aria-current', 'page')
      if (width === 390) await button(page.getByRole('dialog'), '关闭导航').click()
    }

    await page.getByLabel('输出模式').selectOption('report')
    await main.getByRole('button', { name: new RegExp(original.title) }).click()
    await button(main, '发送').click()
    await expect(main.getByText('模拟运行', { exact: true })).toBeVisible()
    for (let step = 0; step < 11; step++) await page.clock.runFor(3300)
    await expectReport(original, /^a\s*>\s*2(?:;|$)/)
    const originalAnswer = await formula.textContent()

    await button(main, '改为两个不同实根').click()
    await expect(question).toHaveText(variant.question)
    await expect(main.getByText('模拟运行', { exact: true })).toBeVisible()
    await expect(main.getByText('0 / 3 步完成', { exact: true })).toBeVisible()
    await expect(reports).toHaveCount(0)
    for (let step = 1; step <= 3; step++) {
      await page.clock.runFor(1300)
      await expect(main.getByText(`${step} / 3 步完成`, { exact: true })).toBeVisible()
    }
    await expectReport(variant, variantAnswer)
    await expect(report.getByText('a = −2 时只有实根 0。', { exact: false })).toBeVisible()
    await expectCurrentTask(variant, original)
    await report.screenshot({ path: fileURLToPath(new URL(`variant-${width}.png`, evidence)) })

    await button(main, '回看原题').click()
    await expectReport(original, originalAnswer)
    await expectCurrentTask(original, variant)
    await report.screenshot({ path: fileURLToPath(new URL(`original-return-${width}.png`, evidence)) })

    await button(main, '查看关联变式').click()
    await expectReport(variant, variantAnswer)
    await expect(main.getByText('3 / 3 步完成', { exact: true })).toBeVisible()
    await expectCurrentTask(variant, original)
    assert.deepEqual(writes, [], 'The simulation must make zero API writes')
    assert.deepEqual(errors, [], 'The dashboard must have no browser errors')
    await page.close()
    console.log(`${width}px passed: independent simulation, two-root result, only x = 0 at a = -2, original restored, same variant reopened, 0 API writes`)
  }
} finally {
  await browser.close()
}
