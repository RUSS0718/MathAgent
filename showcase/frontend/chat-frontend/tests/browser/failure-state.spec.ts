import { expect, test, type Page } from '@playwright/test'

const placeholder = 'No complete answer is available for this run.'
const cases = [
  { name: 'failed unavailable', status: 'failed', presentation_status: 'unavailable', answer: '', title: '未生成答案' },
  { name: 'failed real partial unavailable', status: 'failed', presentation_status: 'unavailable', answer: '已推导出 x = 2，尚未完成其余步骤。', title: '部分结果' },
  { name: 'succeeded real answer unavailable', status: 'succeeded', presentation_status: 'unavailable', answer: '解为 x = 2 或 x = 3。', title: '最终答复' },
  { name: 'failed old placeholder unavailable', status: 'failed', presentation_status: 'unavailable', answer: placeholder, title: '未生成答案' },
  { name: 'failed whitespace unavailable', status: 'failed', presentation_status: 'unavailable', answer: '  \n ', title: '未生成答案' },
  { name: 'failed old placeholder ready', status: 'failed', presentation_status: 'ready', answer: placeholder, title: '未生成答案' },
  { name: 'unknown old placeholder ready', status: 'unknown', presentation_status: 'ready', answer: placeholder, title: '结果状态待确认' },
  { name: 'unknown unavailable', status: 'unknown', presentation_status: 'unavailable', answer: '', title: '结果状态待确认' },
  { name: 'failed whitespace ready', status: 'failed', presentation_status: 'ready', answer: '  \n ', title: '未生成答案' },
  { name: 'failed real partial ready', status: 'failed', presentation_status: 'ready', answer: '已推导出 x = 2，尚未完成其余步骤。', title: '部分结果' },
  { name: 'unknown real partial ready', status: 'unknown', presentation_status: 'ready', answer: '已推导出 x = 2，尚未完成其余步骤。', title: '部分结果' },
  { name: 'succeeded ready', status: 'succeeded', presentation_status: 'ready', answer: '解为 x = 2 或 x = 3。', title: '最终答复' },
  { name: 'succeeded expression failed', status: 'succeeded', presentation_status: 'failed', answer: '解为 x = 2 或 x = 3。', title: '最终答复' },
]

async function mountFixture(page: Page, props: Record<string, unknown>, component: string) {
  // This isolated page mounts only owned components; every API request is intercepted.
  await page.route('**/dashboard-assets/failure-fixture', route => route.fulfill({ contentType: 'text/html', body: `<!doctype html><html lang="zh-CN"><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/dashboard-assets/src/styles/tokens.css"><link rel="stylesheet" href="/dashboard-assets/src/styles/workspace.css"></head><body><main id="fixture"></main><script type="module">
    import { createApp, h } from '/dashboard-assets/node_modules/.vite/deps/vue.js';
    import Component from '/dashboard-assets/src/components/${component}.vue';
    createApp({ render: () => h(Component, ${JSON.stringify(props)}) }).mount('#fixture');
  </script></body></html>` }))
  await page.goto('/dashboard-assets/failure-fixture')
}

for (const scenario of cases) test(scenario.name, async ({ page }, testInfo) => {
  const requests: string[] = []
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const request = route.request()
    requests.push(`${request.method()} ${new URL(request.url()).pathname}`)
    if (request.method() === 'GET' && request.url().endsWith('/run-fixture/answer')) {
      await route.fulfill({ json: { job_id: 'run-fixture', mode: 'solve', ...scenario, notice: scenario.presentation_status === 'unavailable' ? null : '本次求解未完成，当前仅展示已保存内容。' } })
    } else await route.abort()
  })
  await mountFixture(page, { jobId: 'run-fixture', status: scenario.status }, 'FinalAnswer')
  const output = page.locator('#fixture section')
  await expect(output).toHaveAttribute('aria-busy', 'false')
  await page.screenshot({ path: testInfo.outputPath('answer.png'), fullPage: true })
  await expect.soft(output.getByRole('heading', { level: 2 })).toContainText(scenario.title)
  await expect.soft(output).not.toContainText('No complete answer is available')
  if (scenario.answer.trim() && scenario.answer !== placeholder) {
    await expect.soft(output.locator('.report-content')).toContainText(scenario.answer)
    await expect.soft(output).not.toContainText('当前没有可用答复', { timeout: 1000 })
  } else {
    await expect.soft(output.locator('.report-content')).toHaveCount(0)
    await expect.soft(output.getByRole('heading')).not.toContainText('最终答复')
  }
  // Advance past multiple former poll intervals: display/disclosure must not create requests.
  await page.clock.install()
  await page.clock.runFor(6500)
  expect(requests).toEqual(['GET /api/agent/jobs/run-fixture/answer'])
  expect(errors).toEqual([])
})

for (const access of ['allowed', 'denied', 'readonly', 'disabled']) test(`revision ${access}`, async ({ page }) => {
  const requests: string[] = []
  await page.route(url => url.pathname.startsWith('/api/'), route => { requests.push(route.request().url()); return route.abort() })
  await mountFixture(page, {
    jobId: 'run-fixture', sessionId: 'session-fixture', owner: 'fixture', mode: 'solve',
    state: { input_version: 1, revision_allowed: access !== 'denied', revision_source: { task_id: 'source-fixture' } },
    disabled: access === 'disabled', readonly: access === 'readonly',
  }, 'TaskRevisionPanel')
  const panel = page.getByRole('region', { name: '关联任务与改题' })
  await expect(panel.getByRole('link', { name: '查看原任务' })).toBeVisible()
  if (access === 'denied' || access === 'readonly') {
    await expect(panel.locator('summary')).toHaveCount(0)
    await expect(panel.getByRole('textbox')).toHaveCount(0)
  } else {
    await expect.soft(panel.getByRole('textbox')).toBeHidden()
    const summary = panel.locator('summary')
    await expect(summary).toHaveText('改题或追加要求')
    await summary.focus()
    await summary.press('Enter')
    await expect(panel.getByRole('textbox')).toBeVisible()
    if (access === 'disabled') await expect(panel.getByRole('textbox')).toBeDisabled()
    else await panel.getByRole('textbox').fill('包含新增条件的完整题目')
    await summary.press('Space')
    await expect(panel.getByRole('textbox')).toBeHidden()
    await summary.press('Enter')
    if (access === 'allowed') await expect(panel.getByRole('textbox')).toHaveValue('包含新增条件的完整题目')
  }
  expect(requests).toEqual([])
})
