import { expect, test } from '@playwright/test'

test('persisted public routes survive refresh without another solver call', async ({ page }, info) => {
  const origin = 'http://127.0.0.1:8195'
  const auth = await (await page.request.get(`${origin}/api/check_auth`)).json()
  const headers = { 'X-CSRF-Token': auth.csrf_token, 'Idempotency-Key': crypto.randomUUID() }
  const session = await (await page.request.post(`${origin}/api/new_chat`, { headers })).json()
  const problem = 'S03 browser root obligations'
  const created = await page.request.post(`${origin}/api/agent/jobs`, { headers, data: {
    session_id: session.new_session_id, message: problem, solver_mode: 'star_limited',
    problem_spec: { specification_version: 1, original_problem: problem, domain: 'integers',
      quantifiers: ['the equality holds'], assumptions: ['integer arithmetic'], directions: ['prove'],
      output_requirements: ['exact value'], auxiliary_goals: [],
      root_obligations: [{ obligation_id: 'root:value', obligation_type: 'universal', statement: 'PRIVATE_ROUTE_ROOT' }] },
  } })
  expect(created.status(), await created.text()).toBe(202)
  const id = (await created.json()).job_id as string
  await expect.poll(async () => (await (await page.request.get(`${origin}/api/agent/jobs/${id}`)).json()).status).toMatch(/succeeded|failed|canceled/)
  const terminal = await (await page.request.get(`${origin}/api/agent/jobs/${id}`)).json()
  await info.attach('terminal.json', { body: JSON.stringify(terminal), contentType: 'application/json' })
  expect(terminal.status, JSON.stringify(terminal)).toBe('succeeded')
  const report = await (await page.request.get(`${origin}/api/agent/jobs/${id}/report`)).json()
  expect(report.solver.solver.progress.routes.items).toHaveLength(1)
  const calls = (await (await page.request.get('http://127.0.0.1:8192')).json())[id]
  await page.goto(`/dashboard-assets/run/${id}`)
  const panel = page.getByLabel('串行路线与裁决')
  await expect(panel).toContainText('主路线')
  await expect(panel).toContainText('最终答案仍需独立候选选择与整题审查')
  await panel.getByText('路线身份与停止原因').click()
  await expect(panel).toContainText(report.solver.solver.progress.routes.items[0].route_id)
  await page.reload()
  await expect(panel).toContainText('主路线')
  await expect(page.locator('body')).not.toContainText('PRIVATE_ROUTE_ROOT')
  expect((await (await page.request.get('http://127.0.0.1:8192')).json())[id]).toBe(calls)
  await page.screenshot({ path: info.outputPath('routes-after-refresh.png'), fullPage: true })
})
