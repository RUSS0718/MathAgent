import assert from 'node:assert/strict'
import test from 'node:test'
import { projectWorkbench } from '../src/runtime/jobs/workbench.ts'
import { decodeSseBlock, SseProtocolError } from '../src/api/events.schemas.ts'

test('ordinary task renders public goals and retained partial work on refresh', () => {
  const state = projectWorkbench([], { solver: { state_revision: 5, progress: {
    plan_version: 1, steps: [{ label: '步骤 1', goal_summary: '建立递推', current: true }],
    partial: { accepted_steps: [], candidates: [], unresolved: ['义务 1'] },
  } } }, false)
  assert.equal(state.steps[0]?.goal, '建立递推')
  assert.deepEqual(state.partial.unresolved, ['义务 1'])
})

test('one projection deduplicates events and replaces complete plan snapshots', () => {
  const event = { id: 1, event: 'solver_progress', data: { type: 'solver_progress',
    role: 'planner', solver_event_type: 'initial_plan_generated',
    solver: { progress: { plan_version: 2, attempt_index: 1, steps: [
      { label: '步骤 1', current: false, reported: true, verdict: 'ACCEPT', valid: true },
      { label: '步骤 2', current: true, reported: false },
    ] } } } }
  const state = projectWorkbench([event, event], null, false)
  assert.equal(state.events.length, 1)
  assert.equal(state.steps.length, 2)
  assert.equal(state.steps[0]?.status, 'pass')
  assert.equal(state.steps[1]?.status, 'active')
  assert.equal(state.source, 'UNKNOWN · 来源待确认')
  assert.equal(projectWorkbench([], { execution_mode: 'fake' }, true).source, 'FAKE · 模拟数据')
  assert.equal(projectWorkbench([], { execution_mode: 'live' }, true).source, 'REPLAY · 历史重放')
})

test('an older task detail cannot overwrite a newer event plan', () => {
  const event = { id: 8, event: 'solver_progress', data: { type: 'solver_progress', solver_revision: 8,
    solver: { progress: { plan_version: 2, steps: [{ label: '步骤 1', current: true }] } } } }
  const detail = { solver: { state_revision: 3, progress: { plan_version: 1, steps: [] } } }
  assert.equal(projectWorkbench([event], detail, false).steps.length, 1)
})

test('public SSE rejects malformed collaboration and unverified evidence claims', () => {
  const decode = (extra: Record<string, unknown>) => decodeSseBlock({
    event: 'solver_progress', id: '1', hasIdField: true,
    data: JSON.stringify({ type: 'solver_progress', ...extra }),
  })
  const message = { version: 'workbench-v1', thread_id: 'thread-1', message_id: 'message-1',
    from_role: 'step_verifier', to_role: 'reasoner', kind: 'challenge', summary: '本步收到质疑',
    content_status: 'not_published', thread_status: 'open', plan_version: 1, attempt_index: 0 }
  assert.doesNotThrow(() => decode({ workbench: message }))
  assert.doesNotThrow(() => decode({ evidence_chain: [{ step_label: '步骤 1', verdict: 'ACCEPT', valid: true }] }))
  for (const invalid of [
    { workbench: { ...message, thread_id: '' } },
    { workbench: { ...message, version: 'prototype' } },
    { workbench: { ...message, changes: [{ op: 'add', step_label: '步骤 2', summary: '未来重算' }] } },
    { evidence_chain: [{ step_label: '步骤 1', verdict: 'ACCEPT', valid: false }] },
  ]) assert.throws(() => decode(invalid), SseProtocolError)
})
