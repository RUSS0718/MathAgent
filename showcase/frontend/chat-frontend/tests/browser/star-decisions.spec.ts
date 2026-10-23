import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import { mockWorkspace } from './fixtures'

const privateHint = 'PRIVATE HINT TEXT'
const privatePrompt = 'PRIVATE PROMPT TEXT'
const privateClaim = 'PRIVATE CLAIM TEXT'

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
  solverEvent(5, 'step_reviewed', { step_id: 'sum', goal_gate: 'YES', logic_gate: 'PASS', verdict: 'ACCEPT', valid: true }),
  solverEvent(6, 'step_reviewed', { step_id: 'next', goal_gate: 'NO', logic_gate: 'PASS', verdict: 'ACCEPT', valid: false }),
  'id: 7\nevent: final_result\ndata: {"type":"final_result","data":{},"status":"failed"}\n\n',
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
    await expect(page.getByText('目标 YES · 逻辑 PASS · ACCEPT · 允许推进')).toBeVisible()
    await expect(page.getByText('目标 NO · 逻辑 PASS · ACCEPT · 未允许推进')).toBeVisible()

    const visibleText = await page.locator('body').innerText()
    expect(visibleText).not.toContain(privateHint)
    expect(visibleText).not.toContain(privatePrompt)
    expect(visibleText).not.toContain(privateClaim)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
    expect(consoleProblems).toEqual([])
    await page.screenshot({ path: testInfo.outputPath(`star-decisions-${width}.png`), fullPage: true })
  })
}
