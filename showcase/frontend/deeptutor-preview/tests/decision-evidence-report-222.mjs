import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const { chromium, expect } = createRequire(new URL('../../chat-frontend/package.json', import.meta.url))('@playwright/test')
const dashboard = new URL(process.argv[2] ?? 'http://127.0.0.1:8222/dashboard')
const evidence = new URL('../../../../artifacts/issue222/browser/', import.meta.url)
const title = '参数四次方程的四根之谜'
const problem = '当 a 取何值时，方程 x⁴ − 2ax² + a + 2 = 0 有四个不同实根？若四根从小到大成等差数列，再求 a。'
const answer = String.raw`a>2;\qquad a_{\rm AP}=\frac{25+5\sqrt{97}}{18}`
const modes = [
  ['solve', '求解', '最终答案'],
  ['explore', '探索', '候选路线'],
  ['report', '报告', `求解报告 · ${title}`],
  ['teach', '教学', '先想一想'],
]

await mkdir(evidence, { recursive: true })
const browser = await chromium.launch()
try {
  for (const width of [1280, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 844 }, reducedMotion: 'reduce' })
    const apiWrites = []
    const errors = []
    page.on('request', request => {
      const { pathname } = new URL(request.url())
      if (pathname.startsWith('/api/') && !['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
        apiWrites.push(`${request.method()} ${pathname}`)
      }
    })
    page.on('pageerror', error => errors.push(error.message))
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
    const response = await page.goto(dashboard.href)
    assert.equal(response.status(), 200)
    assert.match(response.headers().server, /Werkzeug/)
    assert.match(await response.text(), /\/dashboard-assets\/workbench\//)
    await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], { origin: dashboard.origin })
    await page.clock.install()

    for (const [mode, label, heading] of modes) {
      await page.getByLabel('输出模式').selectOption(mode)
      await page.getByRole('main').getByRole('button', { name: new RegExp(title) }).click()
      await expect(page.getByRole('textbox', { name: '数学问题' })).toHaveValue(mode === 'solve' ? problem : `/${mode} ${problem}`)
      await page.getByRole('button', { name: '发送', exact: true }).click()
      const main = page.getByRole('main')
      const question = main.locator('.question')
      await expect(question).toHaveText(problem)
      await expect(main.getByText('模拟运行', { exact: true })).toBeVisible()
      await expect(main.getByRole('article')).toHaveCount(0)
      for (let step = 1; step <= 11; step++) {
        await page.clock.runFor(3300)
        await expect(main.getByText(`${step} / 11 步完成`, { exact: true })).toBeVisible()
      }
      const article = main.getByRole('article', { name: `${label}模拟答复`, exact: true })
      await expect(main.getByRole('article')).toHaveCount(1)
      await expect(article.getByRole('heading', { name: heading, exact: true })).toBeVisible()
      await expect(article.getByText(`/${mode}`, { exact: true })).toBeVisible()
      if (mode === 'explore') await article.getByText('查看两条路线的结论', { exact: true }).click()
      if (mode === 'teach') await article.getByText('查看参考解答', { exact: true }).click()
      const result = article.locator('.katex').filter({ has: page.locator('annotation').getByText(answer, { exact: true }) })
      await expect(result).toHaveCount(1)
      await expect(result).toBeVisible()
      await expect(article.locator('.katex-error')).toHaveCount(0)

      const copy = article.getByRole('button', { name: '复制报告' })
      const exportMarkdown = article.getByRole('button', { name: '导出 Markdown' })
      if (mode === 'report') {
        const fields = article.locator('dl.report-fields')
        await expect(fields.locator('dt')).toHaveText(['结论', '推导依据', '复核结果', '检查范围'])
        const [, derivation, review, scope] = await fields.locator('dd').evaluateAll(elements =>
          elements.map(element => [...element.childNodes]
            .filter(node => node.nodeType === Node.TEXT_NODE).map(node => node.textContent).join('').trim()),
        )
        assert.ok(derivation && review && scope, 'All three rendered prose fields must be populated')
        const equation = fields.locator('dd').nth(1).locator('.katex')
        await expect(equation).toBeVisible()
        await expect(equation.locator('annotation')).toHaveText('9a^2-25a-50=0')
        const expected = [
          `# ${await article.locator('h2').innerText()}`,
          `## 题目\n${await question.innerText()}`,
          `## 结论\n$$\n${await result.locator('annotation').textContent()}\n$$`,
          `## 推导依据\n${derivation}\n\n$$\n${await equation.locator('annotation').textContent()}\n$$`,
          `## 复核结果\n${review}`,
          `## 检查范围\n${scope}`,
          '> 本报告来自 MathAgent 本地模拟演示。',
        ].join('\n\n')

        const writesBeforeExport = apiWrites.length
        await copy.click()
        await expect(article.getByRole('status')).toHaveText('报告已复制')
        const clipboard = (await page.evaluate(() => navigator.clipboard.readText())).replaceAll('\r\n', '\n')
        const [download] = await Promise.all([page.waitForEvent('download'), exportMarkdown.click()])
        assert.equal(download.suggestedFilename(), `${title}.md`)
        const downloaded = await readFile(await download.path(), 'utf8')
        assert.equal(clipboard, expected, 'Clipboard Markdown must match the visible report')
        assert.equal(downloaded, expected, 'Downloaded Markdown must match the visible report and clipboard')
        await expect(main.getByRole('article')).toHaveCount(1)
        await expect(article).toBeVisible()
        await expect(question).toHaveText(problem)
        await article.screenshot({ path: fileURLToPath(new URL(`report-${width}.png`, evidence)) })
        assert.equal(apiWrites.length, writesBeforeExport, `Export made an API write: ${apiWrites.slice(writesBeforeExport)}`)
        await download.saveAs(fileURLToPath(new URL(`download-${width}.md`, evidence)))
        await writeFile(new URL(`clipboard-${width}.md`, evidence), clipboard, 'utf8')
      } else {
        await expect(copy).toHaveCount(0)
        await expect(exportMarkdown).toHaveCount(0)
      }
      await main.getByRole('button', { name: '新建题目', exact: true }).click()
    }
    assert.deepEqual(errors, [])
    assert.deepEqual(apiWrites, [], 'The entire local simulation must make zero API writes, including solve requests')
    await page.close()
    console.log(`${width}px passed: four single-mode answers, clipboard and download match the rendered report, 0 API writes`)
  }
} finally {
  await browser.close()
}
