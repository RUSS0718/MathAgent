import assert from 'node:assert/strict'
import test from 'node:test'
import { projectWorkbench } from '../src/runtime/jobs/workbench.ts'

const event = (id: number, type: string, data: Record<string, unknown> = {}) => ({ id, event: 'solver_progress', data: { solver_event_type: type, ...data } })
test('2000 internal saves stay traceable without flooding meaningful progress', () => {
  const events = [event(1, 'initial_plan_generated', { role: 'planner', plan_version: 1 }),
    ...Array.from({ length: 2000 }, (_, i) => event(i + 2, 'state_saved', { role: 'controller' })),
    event(2002, 'step_reported', { role: 'reasoner', step_id: '步骤 1' })]
  const state = projectWorkbench([...events, ...events], null, false)
  assert.equal(state.events.length, 2002)
  assert.equal(state.keyEntries.length, 2)
  assert.equal(state.entries.filter(e => e.role === 'unknown').length, 0)
  assert.equal(projectWorkbench([event(1, 'future_kind')], null, false).entries[0]?.role, 'unknown')
})
test('semantic duplicates collapse but changed attempts and verdicts survive', () => {
  const events = [event(1, 'step_reviewed', { step_id: '步骤 1', verdict: 'CHALLENGE', attempt_index: 0 }),
    event(2, 'step_reviewed', { step_id: '步骤 1', verdict: 'CHALLENGE', attempt_index: 0 }),
    event(3, 'step_reviewed', { step_id: '步骤 1', verdict: 'ACCEPT', attempt_index: 0 }),
    event(4, 'step_reviewed', { step_id: '步骤 1', verdict: 'ACCEPT', attempt_index: 1 })]
  assert.equal(projectWorkbench(events, null, false).keyEntries.length, 3)
})
test('concurrent calls keep role running until each settles; history never animates execution', () => {
  const events = [event(1, 'call_audit', { role: 'reasoner', solver_call_id: 'a', call_lifecycle: 'running' }),
    event(2, 'call_audit', { role: 'reasoner', solver_call_id: 'b', call_lifecycle: 'running' }),
    event(3, 'call_audit', { role: 'reasoner', solver_call_id: 'a', call_lifecycle: 'completed' })]
  assert.equal(projectWorkbench(events, null, false).roleStates.reasoner, 'running')
  assert.equal(projectWorkbench(events, null, true).roleStates.reasoner, 'unknown')
  events.push(event(4, 'call_audit', { role: 'reasoner', solver_call_id: 'b', call_lifecycle: 'failed' }))
  assert.equal(projectWorkbench(events, null, false).roleStates.reasoner, 'failed')
  assert.equal(projectWorkbench(events, null, false).roleStates.planner, 'idle')
})
test('critical states survive unknown types and use safe categorical text', () => {
  for (const status of ['waiting_input', 'failed', 'canceled', 'unknown', 'needs_review']) {
    const state = projectWorkbench([event(1, 'new_kind', { status, summary: 'PRIVATE' })], null, false)
    assert.equal(state.keyEntries.length, 1)
    assert.ok(!state.keyEntries[0]?.summary.includes('PRIVATE'))
  }
})
test('legacy call failures remain visible and prototype names are never roles or progress', () => {
  const old = projectWorkbench([event(1, 'call_audit', { role: 'planner', solver_call_id: 'a', call_status: 'failed' })], null, false)
  assert.equal(old.roleStates.planner, 'failed')
  assert.equal(old.keyEntries.length, 1)
  const unknown = projectWorkbench([event(1, 'constructor', { role: 'constructor' })], null, false)
  assert.equal(unknown.entries[0]?.role, 'unknown')
  assert.equal(unknown.keyEntries.length, 0)
})
test('legacy unknown to failed survives dedup and role-only failures agree with text', () => {
  const events = ['unknown', 'failed'].map((status, i) => event(i + 1, 'call_audit', { role: 'planner', solver_call_id: 'a', call_status: status }))
  assert.equal(projectWorkbench(events, null, false).keyEntries.length, 2)
  for (const status of ['failed', 'unknown']) {
    assert.equal(projectWorkbench([event(1, 'future', { role: 'planner', status })], null, false).roleStates.planner, status)
  }
})
