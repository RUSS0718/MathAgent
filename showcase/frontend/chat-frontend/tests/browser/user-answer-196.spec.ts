import { expect, test } from '@playwright/test'
import { mockWorkspace } from './fixtures'

test('196 final answer waits for saved output and restores by GET only', async ({ page }) => {
  await mockWorkspace(page, true)
  let reads = 0
  const mutations: string[] = []
  page.on('request', request => { if (request.method() === 'POST' && /run-demo/.test(request.url())) mutations.push(request.url()) })
  await page.route('**/api/agent/jobs/run-demo/answer', route => {
    reads++
    return route.fulfill(reads === 1 ? { status: 404, json: { error: '尚未保存' } } : { json: { job_id: 'run-demo', status: 'succeeded', mode: 'teach', answer: reads === 2 ? '' : '唯一教学答复', presentation_status: reads === 2 ? 'pending' : 'ready', notice: '仅覆盖已完成步骤。' } })
  })
  await page.goto('/dashboard-assets/session/session-demo')
  await expect(page.getByRole('region', { name: '最终答复' })).toContainText('唯一教学答复', { timeout: 10000 })
  await expect(page.getByText('唯一教学答复', { exact: true })).toHaveCount(1)
  await expect(page.getByRole('button', { name: /生成模板|表达内容|原答案/ })).toHaveCount(0)
  await expect(page.getByText('技术详情', { exact: false })).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('region', { name: '最终答复' })).toContainText('唯一教学答复')
  expect(mutations).toEqual([])
})
import AxeBuilder from '@axe-core/playwright'

for (const mode of ['solve', 'teach', 'report']) test(`196 ${mode} displays one saved answer`, async ({ page }) => {
  await mockWorkspace(page, true)
  await page.route('**/api/agent/jobs/run-demo/answer', r => r.fulfill({ json: { job_id: 'run-demo', status: 'succeeded', mode, answer: '保存的答复', presentation_status: 'ready', notice: '尚未验证整题。' } }))
  await page.goto('/dashboard-assets/session/session-demo')
  await expect(page.getByRole('region', { name: '最终答复' })).toContainText('保存的答复')
  await expect(page.getByText('保存的答复', { exact: true })).toHaveCount(1)
})
for (const state of ['failed', 'stale', 'legacy', 'unavailable']) test(`196 ${state} preserves boundary`, async ({ page }) => {
  await mockWorkspace(page, true)
  await page.route('**/api/agent/jobs/run-demo/answer', r => r.fulfill({ json: { job_id: 'run-demo', status: 'failed', mode: 'report', answer: state === 'unavailable' ? '' : '已有部分成果', presentation_status: state, notice: '未完成全部目标。' } }))
  await page.goto('/dashboard-assets/session/session-demo')
  const output = page.getByRole('region', { name: '最终答复' })
  await expect(output).toContainText('未完成全部目标。')
  await expect(output).toContainText({ failed: '生成失败', stale: '来源已变化', legacy: '历史结果', unavailable: '没有可用答复' }[state]!)
})
test('196 narrow final answer retains filters plan star replay and accessibility', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 })
  await mockWorkspace(page, true)
  await page.route('**/api/agent/jobs/run-demo/answer', r => r.fulfill({ json: { job_id: 'run-demo', status: 'succeeded', mode: 'solve', answer: '可读答复', presentation_status: 'ready', notice: '有限检查。' } }))
  await page.goto('/dashboard-assets/session/session-demo')
  await expect(page.getByRole('region', { name: '最终答复' })).toContainText('可读答复')
  await page.getByText('求解过程', { exact: true }).click()
  await expect(page.getByRole('combobox', { name: '角色', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '完整星图', exact: true }).click()
  await expect(page.getByText('求解计划与调度详情')).toBeVisible()
  await page.getByText('查看历史回放').click()
  await expect(page.getByLabel('回放位置（不是求解进度）')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.screenshot({ path: '../../../artifacts/user-solving-196/narrow.png', fullPage: true })
})
test('196 ordinary technical deeplink never mounts technical requests', async ({ page }) => {
  await mockWorkspace(page)
  const requests: string[] = []
  page.on('request', r => { if (/\/api\/.*run-demo/.test(r.url())) requests.push(r.url()) })
  await page.goto('/dashboard-assets/run/run-demo')
  await expect(page.getByRole('heading', { name: '技术审阅需要授权' })).toBeVisible()
  expect(requests).toEqual([])
})
