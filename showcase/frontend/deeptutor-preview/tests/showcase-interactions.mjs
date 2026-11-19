import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdir } from 'node:fs/promises'
const { chromium, expect } = createRequire(new URL('../../chat-frontend/package.json', import.meta.url))('@playwright/test')
const out = '../../../artifacts/deeptutor-interactive'
await mkdir(out, { recursive: true })
const browser = await chromium.launch()
const checks = []
async function scenario(name, run) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, reducedMotion: 'reduce' })
  try {
    await page.goto((process.env.SHOWCASE_URL ?? 'http://127.0.0.1:3090') + '/dashboard')
    await page.getByLabel('数学问题').waitFor()
    await run(page)
    checks.push([name, 'PASS'])
  } catch (err) { checks.push([name, 'FAIL', err.message.split('\n').slice(0,4).join(' ')]) }
  finally { await page.close() }
}
const btn = (p, name) => p.getByRole('button', { name, exact: true })
const visible = locator => expect(locator).toBeVisible({ timeout: 1800 })
async function start(page, title) {
  await page.clock.install()
  await page.clock.pauseAt(new Date(Date.now() + 1500))
  await page.locator('.suggestions').getByRole('button', { name: title }).click({ timeout: 1800 })
  await btn(page, '发送').click()
}
async function advance(page, n, ms) {
  for (let i=0; i<n; i++) await page.clock.runFor(ms)
}
try {
  await scenario('四次方程的消息、依据、追问和变式', async page => {
    await page.getByLabel('输出模式').selectOption('report')
    await start(page, /四次方程/)
    await advance(page, 6, 3250)
    const line = page.getByRole('button', { name: '质疑 · 步骤校验 → 元策略' })
    await visible(line)
    await line.click()
    const detail = page.getByRole('region', { name:'决策依据' })
    await expect(detail).toContainText('a = −3')
    await expect(detail).toContainText('修正待发布')
    await advance(page, 5, 3250)
    await expect(detail).toContainText('a > 2')
    await btn(page,'为什么 a = 2 也不行？').click()
    await expect(page.getByRole('region',{name:'步骤追问'})).toContainText('两个不同实根')
    await expect(page.getByRole('button',{name:'查看推理阶段成果'})).toHaveAttribute('data-highlight','true')
    await btn(page,'改为两个不同实根').click()
    await advance(page,3,1300)
    await expect(page.getByRole('article')).toContainText('−2')
    await btn(page,'回看原题').click()
    await expect(page.getByRole('article',{name:'报告模拟答复'})).toBeVisible()
    await btn(page,'查看关联变式').click()
    await expect(page.locator('.question')).toContainText('恰有两个')
  })
  await scenario('同题补充不同尺寸', async page => {
    await start(page, /三角形/)
    await visible(page.getByRole('region',{name:'补充条件'}))
    await page.getByLabel('底（厘米）').fill('8')
    await page.getByLabel('对应的高（厘米）').fill('5')
    await btn(page,'补充并继续').click()
    await advance(page,3,1300)
    await expect(page.getByRole('article')).toContainText('20')
    await expect(page.locator('.question')).toContainText('求这个三角形')
  })
  await scenario('公开成果摘录只读回放', async page => {
    const writes=[]; page.on('request',r=>{if(r.method()==='POST')writes.push(r.url())})
    await btn(page,'D2 公开成果摘录').click({timeout:1800})
    await visible(page.getByRole('heading',{name:'参数传递与复核'}))
    await btn(page,'下一步').click(); await expect(page.getByRole('region',{name:'历史成果'})).toContainText('x² − 3x + 2 = 0')
    await page.reload(); await visible(page.getByRole('heading',{name:'参数传递与复核'})); await expect(page.getByRole('region',{name:'历史成果'})).toContainText('步骤 2 / 3'); assert.deepEqual(writes,[])
  })
  await scenario('独立预览只展示题图样例', async page => {
    const apiRequests = []
    page.on('request', request => {
      if (new URL(request.url()).pathname.startsWith('/api/')) apiRequests.push(request.url())
    })
    await btn(page,'题图求解').click()
    await visible(page.getByRole('img', { name: /示例题图/ }))
    await expect(btn(page,'发送题图')).toHaveCount(0)
    for (const hash of ['#submit/pending', '#image/pending/example', '#image/run/example']) {
      await page.goto(new URL(hash, page.url()).href)
      await expect(btn(page,'核对原提交')).toHaveCount(0)
    }
    assert.deepEqual(apiRequests, [])
    assert.equal((await page.request.get(new URL('/api/capabilities', page.url()).href)).status(), 404)
  })
} finally { await browser.close() }
for (const check of checks) console.log(check.join(' | '))
if(checks.some(([,status])=>status==='FAIL')) process.exitCode=1
