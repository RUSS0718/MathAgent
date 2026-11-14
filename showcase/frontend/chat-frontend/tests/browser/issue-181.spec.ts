import { expect, test } from '@playwright/test'
import { mockWorkspace, report } from './fixtures'
for (const frozen of [false, true]) test(`181 ${frozen ? 'frozen' : 'ordinary'} reads never generate; explicit failure preserves answer`, async ({ page }) => {
  await mockWorkspace(page, true)
  let posts = 0, reads = 0
  await page.route('**/api/agent/jobs/run-demo', route => route.fulfill({ json: {
    success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'succeeded', last_event_id: 0,
    result: { ...(frozen ? { presentation_mode: 'teach' } : {}), faithful: { version: 'faithful-task-v1' } },
  } }))
  await page.route('**/api/agent/jobs/run-demo/outputs/*', route => {
    reads++; expect(route.request().method()).toBe('GET')
    return route.fulfill({ status: 404, json: { code: 'presentation_unavailable' } })
  })
  for (const mode of ['teach', 'report']) await page.route(`**/api/agent/jobs/run-demo/${mode}`, route => {
    if (route.request().method() !== 'POST') return route.fulfill({ json: report })
    posts++; return route.fulfill({ status: 503, json: { error: '模板暂不可用' } })
  })
  await page.goto('/dashboard-assets/session/session-demo')
  const output = page.getByRole('region', { name: 'S06 输出模式' })
  await expect(output).toBeVisible()
  await expect.poll(() => reads).toBeGreaterThan(0)
  expect(posts).toBe(0)
  if (frozen) await expect(output.getByLabel('表达模式')).toHaveCount(0)
  if (!frozen) await output.getByLabel('表达模式').selectOption('report')
  await output.getByRole('button', { name: '表达内容', exact: true }).click()
  await expect(output).toContainText('尚未保存')
  expect(posts).toBe(0)
  await output.getByRole('button', { name: '生成模板', exact: false }).click()
  await expect(output).toContainText('模板暂不可用')
  expect(posts).toBe(1)
  await output.getByRole('button', { name: '原答案', exact: true }).click()
  await expect(output.getByLabel('原答案内容')).toContainText('最终答案')
  await page.reload()
  await expect(output).toBeVisible()
  await expect.poll(() => reads).toBeGreaterThan(1)
  expect(posts).toBe(1)
})

for (const path of ['/dashboard-assets/session/session-demo', '/dashboard-assets/run/run-demo']) test('181 explicit success restores saved output: ' + path, async ({ page }) => {
  await mockWorkspace(page, true)
  let posts = 0, reads = 0, saved = false
  await page.route('**/api/agent/jobs/run-demo', route => route.fulfill({ json: {
    success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'succeeded', last_event_id: 0,
    result: { faithful: { version: 'faithful-task-v1' } },
  } }))
  const artifact = {
    schema_version: 'test', policy_version: 'test', job_id: 'run-demo', mode: 'teach', status: 'ready',
    answer: report.report.answer, answer_artifact: {}, source_fingerprint: 'test', source_versions: {},
    sources: [], paragraphs: [{ id: 'paragraph:1', version: 1, text: '模板原文整理', kind: 'editorial',
      claim_refs: [], status: 'current', grade: 'not_verified', binding: 'editorial' }],
    budget: null, request_attempts: [], scope: { covered: 0, total: 0, unresolved: [] },
    completion: 'partial', formal_verification: 'not_verified', revalidation_reason: null, renderer: 'template',
    output_request: { id: 'output:test', kind: 'presentation_only', model_calls: 0, solver_resumed: false },
    artifact: { schema: 'test', sha256: 'test', id: 'presentation:test' },
  }
  const result = { version: '1', evidence_id: 'run-demo', status: 'succeeded', mode: 'teach',
    answer: report.report.answer, presentation: artifact, presentation_history: [], report: report.report }
  await page.route('**/api/agent/jobs/run-demo/outputs/teach', route => {
    reads++; expect(route.request().method()).toBe('GET')
    return route.fulfill(saved ? { json: result } : { status: 404, json: { code: 'presentation_unavailable' } })
  })
  await page.route('**/api/agent/jobs/run-demo/teach', route => {
    expect(route.request().method()).toBe('POST'); posts++; saved = true
    return route.fulfill({ json: result })
  })
  await page.goto(path)
  const output = page.getByRole('region', { name: 'S06 输出模式' })
  await expect(output).toContainText('尚未保存')
  await output.getByRole('button', { name: '生成模板教学' }).click()
  await expect(output).toContainText('模板原文整理')
  await expect(output).toHaveAttribute('data-artifact-id', 'presentation:test')
  await expect(output).toContainText('未知 / 未记录')
  await expect(output).toContainText('实验性模板整理')
  await expect(output.getByRole('link', { name: '段落版本与证据' })).toHaveCount(0)
  await page.reload()
  await expect(output).toHaveAttribute('data-artifact-id', 'presentation:test')
  await output.getByRole('button', { name: '表达内容', exact: true }).click()
  await expect(output).toContainText('模板原文整理')
  expect(posts).toBe(1); expect(reads).toBeGreaterThan(1)
})
