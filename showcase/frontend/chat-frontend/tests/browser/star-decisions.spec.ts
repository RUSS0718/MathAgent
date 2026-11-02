import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import { mockWorkspace } from './fixtures'

const privateHint = 'PRIVATE HINT TEXT'
const privatePrompt = 'PRIVATE PROMPT TEXT'
const privateClaim = 'PRIVATE CLAIM TEXT'
const privateReasoning = 'PRIVATE HIDDEN REASONING'

function solverEvent(id: number, solverEventType: string, fields: Record<string, unknown>): string {
  const data = {
    type: 'solver_progress',
    solver_event_id: `solver-${id}`,
    solver_revision: id,
    solver_event_type: solverEventType,
    node_name: 'star',
    title: privatePrompt,
    summary: privatePrompt,
    prompt: privatePrompt,
    preplan_hint: privateHint,
    private_step_id: privateHint,
    claims: [privateClaim],
    ...fields,
  }
  return `id: ${id}\nevent: solver_progress\ndata: ${JSON.stringify(data)}\n\n`
}

const starEvents = [
  solverEvent(1, 'explore_assessed', { assessment: 'PARTIALLY_SOLVED', round: 1, next_phase: 'EXPLORE' }),
  solverEvent(2, 'partial_exploration_routed', { decision: 'PLAN', next_phase: 'PLAN' }),
  solverEvent(3, 'solution_review_assessed', { verdict: 'REJECT', next_phase: 'PLAN' }),
  solverEvent(4, 'initial_plan_generated', { plan_version: 1 }),
  // Planner used privateHint as its internal ID; the expected SSE projection is a plan ordinal.
  solverEvent(5, 'step_reviewed', { step_id: '步骤 1', goal_gate: 'YES', logic_gate: 'PASS', verdict: 'ACCEPT', valid: true }),
  solverEvent(6, 'step_reviewed', { step_id: '步骤 2', goal_gate: 'NO', logic_gate: 'PASS', verdict: 'ACCEPT', valid: false }),
  solverEvent(7, 'step_reviewed', {
    step_id: '步骤 1', goal_gate: 'PARTIAL', logic_gate: 'UNCERTAIN', verdict: 'CHALLENGE',
    valid: true, role: 'step_verifier', objection_summary: '检查边界项的符号。',
    usage: { prompt_tokens: 7, completion_tokens: 3, total_tokens: 10 },
    argument: privateReasoning,
  }),
  solverEvent(8, 'challenge_replied', {
    round: 1, role: 'reasoner',
    usage: { prompt_tokens: 7, completion_tokens: 3, total_tokens: 10 },
    argument: privateReasoning,
  }),
  solverEvent(9, 'challenge_stalemate', {
    role: 'controller', upgrade_reason: 'round_limit_reached', reason: privateReasoning,
  }),
  solverEvent(10, 'meta_decided', {
    role: 'meta', decision: 'ABORT', upgrade_reason: 'round_limit_reached',
    usage: { prompt_tokens: 7, completion_tokens: 3, total_tokens: 10 },
    reason_summary: privateReasoning,
  }),
  'id: 11\nevent: final_result\ndata: {"type":"final_result","data":{},"status":"failed"}\n\n',
].join('')

for (const width of [320, 768, 1024, 1440]) {
  test(`STAR route and Gate decisions render safely at ${width}px`, async ({ page }, testInfo) => {
    const consoleProblems: string[] = []
    page.on('pageerror', (error) => consoleProblems.push(error.message))
    page.on('console', (message) => {
      if (['error', 'warning'].includes(message.type())) consoleProblems.push(message.text())
    })
    await page.setViewportSize({ width, height: 1000 })
    await mockWorkspace(page, true, starEvents)
    await page.goto('/dashboard-assets/run/run-demo')

    await expect(page.getByText('第 1 轮 探索：部分解决 → 继续探索')).toBeVisible()
    await expect(page.getByText('Meta 决策：转入计划')).toBeVisible()
    await expect(page.getByText('整题审查：REJECT → 生成计划')).toBeVisible()
    await expect(page.getByText('计划 v1 已生成')).toBeVisible()
    await expect(page.getByText('步骤 1 · 目标 YES · 逻辑 PASS · ACCEPT · 允许推进')).toBeVisible()
    await expect(page.getByText('步骤 2 · 目标 NO · 逻辑 PASS · ACCEPT · 未允许推进')).toBeVisible()
    await expect(page.getByText(/异议：检查边界项的符号。/)).toBeVisible()
    await expect(page.getByText(/Reasoner · 已回应异议 · 用量：输入 7 · 输出 3 · 合计 10 tokens/)).toBeVisible()
    await expect(page.getByText(/达到质询轮数上限 · 升级原因：轮数上限 · 已升级 Meta/)).toBeVisible()
    await expect(page.getByText(/Meta 裁定 ABORT · 升级原因：轮数上限 · 用量：输入 7 · 输出 3 · 合计 10 tokens/)).toBeVisible()

    const visibleText = await page.locator('body').innerText()
    expect(visibleText).not.toContain(privateHint)
    expect(visibleText).not.toContain(privatePrompt)
    expect(visibleText).not.toContain(privateClaim)
    expect(visibleText).not.toContain(privateReasoning)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
    expect(consoleProblems).toEqual([])
    await page.screenshot({ path: testInfo.outputPath(`star-decisions-${width}.png`), fullPage: true })
  })
}

test('raw Planner step IDs are never rendered as Gate labels', async ({ page }) => {
  const privateStepEvents = starEvents.replace(
    '"step_id":"步骤 1"',
    `"step_id":"${privateHint}"`,
  )
  await mockWorkspace(page, true, privateStepEvents)
  await page.goto('/dashboard-assets/run/run-demo')

  const visibleText = await page.locator('body').innerText()
  expect(visibleText).not.toContain(privateHint)
  expect(visibleText).not.toContain(privateReasoning)
  await expect(page.getByText('目标 YES · 逻辑 PASS · ACCEPT · 允许推进')).toBeVisible()
})
