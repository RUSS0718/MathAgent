import { expect, test, type Page } from '@playwright/test'
import { writeFile } from 'node:fs/promises'

type Fixture = {
  run_id: string
  output_id: string
  artifact_id: string
  paragraph_id: string
  graph_version: number
  node_id: string
  execution_mode: string
  graph_origin: string
  paragraph_ids: string[]
  node_count: number
  provider_calls: number
  public_detail: unknown
}

async function prepare(page: Page, synthetic = false): Promise<Fixture> {
  const auth = await page.request.get('http://127.0.0.1:8096/api/check_auth')
  expect(auth.ok()).toBe(true)
  const response = await page.request.post(`http://127.0.0.1:8096/__test__/f7/fixture?synthetic=${synthetic}`, {
    headers: { 'X-CSRF-Token': (await auth.json()).csrf_token },
  })
  expect(response.ok(), await response.text()).toBe(true)
  return await response.json() as Fixture
}

function deepLink(fixture: Fixture): string {
  const query = new URLSearchParams({
    scheme: 'f7-deeplink-v1', run: fixture.run_id,
    output: fixture.output_id, artifact: fixture.artifact_id,
    graph: String(fixture.graph_version), node: fixture.node_id,
    paragraph: fixture.paragraph_id, mode: 'teach',
  })
  return `/dashboard/system?${query.toString()}`
}

function trackWrites(page: Page): string[] {
  const writes: string[] = []
  page.on('request', request => {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
      writes.push(`${request.method()} ${new URL(request.url()).pathname}`)
    }
  })
  return writes
}

test('real persisted F6 output restores every paragraph and node deep link without writes', async ({ page, context, browser }, testInfo) => {
  const fixture = await prepare(page)
  expect(fixture.execution_mode).toBe('star_limited')
  expect(fixture.graph_origin).toBe('real_harness')
  expect(fixture.provider_calls).toBeGreaterThan(0)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
  const writes = trackWrites(page)
  const url = deepLink(fixture)
  const withoutMode = new URL(url, 'http://127.0.0.1:8096')
  withoutMode.searchParams.delete('mode')
  await page.goto(withoutMode.toString())
  await expect(page.getByText(`产物身份：${fixture.artifact_id}`, { exact: true })).toBeVisible()

  for (const paragraphId of fixture.paragraph_ids) {
    await page.goto(deepLink({ ...fixture, paragraph_id: paragraphId }))
    await expect(page.getByRole('heading', { name: fixture.run_id })).toBeVisible()
    await expect(page.getByText(`独立输出身份：${fixture.output_id}`, { exact: true })).toBeVisible()
    await expect(page.locator(`#f7-${paragraphId.replace(':', '-')}`)).toBeVisible()
    await page.reload()
    await expect(page.locator(`#f7-${paragraphId.replace(':', '-')}`)).toBeVisible()
    await expect(page.locator(`#f7-${paragraphId.replace(':', '-')}`)).toHaveAttribute('aria-current', 'location')
    await expect(page.getByLabel('保存的验证等级')).toContainText('REVIEWED')
    if (process.env.F7_FORMAL_GRADE) {
      await expect(page.getByLabel('保存的验证等级')).toContainText(`VERIFIED ${process.env.F7_FORMAL_GRADE}`)
    }
  }
  const svg = page.locator(`svg[data-node-count="${fixture.node_count}"]`)
  await expect(svg).toHaveAttribute('data-render-ms', /\d/)
  await expect(svg.locator('circle.is-selected')).toHaveCount(1)
  const realRenderMs = Number(await svg.getAttribute('data-render-ms'))

  const reopened = await context.newPage()
  const reopenedWrites = trackWrites(reopened)
  await reopened.goto(url)
  await expect(reopened.locator(`#f7-${fixture.paragraph_id.replace(':', '-')}`)).toBeVisible()
  await expect(reopened.getByText(`产物身份：${fixture.artifact_id}`, { exact: true })).toBeVisible()
  await reopened.close()

  expect(writes).toEqual([])
  expect(reopenedWrites).toEqual([])
  expect(errors).toEqual([])
  const evidencePath = testInfo.outputPath('f7-real-run.json')
  await writeFile(evidencePath, JSON.stringify({ fixture, browser_version: browser.version(), real_render_ms: realRenderMs }, null, 2))
  await testInfo.attach('f7-real-run.json', { path: evidencePath, contentType: 'application/json' })
  await page.screenshot({ path: testInfo.outputPath('f7-system-view-desktop.png'), fullPage: true })
})

test('synthetic 500 node graph renders within the frozen budget', async ({ page, browser }, testInfo) => {
  const fixture = await prepare(page, true)
  expect(fixture.graph_origin).toBe('synthetic_f7_performance')
  const writes = trackWrites(page)
  const renderTimes: number[] = []
  for (let repeat = 0; repeat < 3; repeat += 1) {
    await page.goto(deepLink(fixture))
    await expect(page.getByText('这是 synthetic 500 节点性能样本，不代表真实 Run 的数学依赖图。')).toBeVisible()
    const svg = page.locator('svg[data-node-count="500"]')
    await expect(svg).toHaveAttribute('data-render-ms', /\d/)
    const milliseconds = Number(await svg.getAttribute('data-render-ms'))
    renderTimes.push(milliseconds)
    expect(milliseconds).toBeLessThanOrEqual(2000)
    await expect(page.locator('a[aria-label^="节点 p500"]')).toBeVisible()
  }
  expect(writes).toEqual([])
  const sorted = [...renderTimes].sort((a, b) => a - b)
  const metricsPath = testInfo.outputPath('f7-500-node-render-metrics.json')
  await writeFile(metricsPath, JSON.stringify({ source: fixture.graph_origin, nodes: 500, edges: 499,
      browser_version: browser.version(), viewport: { width: 1440, height: 1000 },
      repetitions: 3, render_ms: renderTimes, p50_ms: sorted[1], p95_ms: sorted[2], threshold_ms: 2000 }, null, 2))
  await testInfo.attach('f7-500-node-render-metrics.json', { path: metricsPath, contentType: 'application/json' })
})

test('real F6 artifact deep link remains usable on mobile and the Run list loads from SQLite', async ({ page }, testInfo) => {
  const fixture = await prepare(page)
  const writes = trackWrites(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/dashboard/system')
  await expect(page.getByText(fixture.run_id, { exact: true })).toBeVisible()
  await page.getByRole('link', { name: fixture.run_id }).click()
  await expect(page.getByRole('heading', { name: fixture.run_id })).toBeVisible()
  await page.getByLabel('已保存输出').getByRole('link').first().click()
  await expect(page.locator(`#f7-${fixture.paragraph_id.replace(':', '-')}`)).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  expect(writes).toEqual([])
  await page.screenshot({ path: testInfo.outputPath('f7-system-view-mobile.png'), fullPage: true })
})

test('unknown identities retain the Run and inference nodes have restorable links', async ({ page }) => {
  const fixture = await prepare(page)
  const writes = trackWrites(page)
  const nodeUrl = new URL(deepLink(fixture), 'http://127.0.0.1:8096')
  nodeUrl.searchParams.delete('paragraph')
  nodeUrl.searchParams.set('node', 'a1')
  await page.goto(nodeUrl.toString())
  await expect(page.locator('#f7-node-a1 rect.is-selected')).toBeVisible()
  await page.reload()
  await expect(page.locator('#f7-node-a1 rect.is-selected')).toBeVisible()
  await page.goto(deepLink({ ...fixture, paragraph_id: 'paragraph:99999' }))
  await expect(page.getByText('段落身份不存在于指定产物；保留当前 Run 和产物。')).toBeVisible()
  await expect(page.getByRole('heading', { name: fixture.run_id })).toBeVisible()
  await page.goto(deepLink({ ...fixture, artifact_id: 'presentation:missing' }))
  await expect(page.getByText('指定的 F6 输出身份不存在；已保留当前 Run。')).toBeVisible()
  await expect(page.getByLabel('F6 交付物')).toHaveCount(0)
  expect(writes).toEqual([])
})
