import assert from 'node:assert/strict'
import test from 'node:test'
import { projectWorkbench } from '../src/runtime/jobs/workbench.ts'
const event = (id: number, type: string, data: Record<string, unknown> = {}) => ({ id, event: 'solver_progress', data: { solver_event_type: type, ...data } })
test('ordinary routing explains actual changes without completing roles', () => {
  const state = projectWorkbench([
    event(1, 'adaptive_planning_required', { routing_summary: '题目中的目标有先后依赖，先制定分步方案。' }),
    event(2, 'adaptive_planning_required', { routing_summary: '本次探索达到输出上限，转入制定方案。' }),
  ], null, false, 'running')
  assert.equal(state.keyEntries.length, 2)
  assert.equal(state.keyEntries[0]?.summary, '题目中的目标有先后依赖，先制定分步方案。')
  assert.equal(state.roleStates.planner, 'idle')
  assert.equal(state.roleStates.reasoner, 'idle')
})
test('ordinary direct review never treats the candidate as proven', () => {
  const state = projectWorkbench([event(1, 'explore_assessed', {
    routing_summary: '已形成完整候选，交由独立答案审查。', role: 'explore',
  })], null, false)
  assert.equal(state.keyEntries[0]?.summary, '已形成完整候选，交由独立答案审查。')
  assert.equal(state.roleStates.planner, 'idle')
  assert.equal(state.roleStates.whole_solution_verifier, 'idle')
})
test('unrecognized route text is never displayed', () => {
  const state = projectWorkbench([event(1, 'adaptive_planning_required', { routing_summary: 'PRIVATE' })], null, false)
  assert.equal(state.keyEntries.length, 1)
  assert.ok(!state.keyEntries[0]?.summary.includes('PRIVATE'))
})
