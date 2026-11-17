import assert from 'node:assert/strict'
import test from 'node:test'
import { projectWorkbench } from '../src/runtime/jobs/workbench.ts'
import { statusLabels } from '../src/runtime/jobs/causal-progress.ts'

const progress = { plan_version: 1, steps: [
  { label: 'S1', current: true, reported: true },
  { label: 'S2', current: false, reported: false },
  { label: 'S3', verdict: 'ACCEPT', valid: true },
  { label: 'S4', verdict: 'CHALLENGE', current: true },
] }
const result = { solver: { state_revision: 1, progress } }

test('failed public Job shows ended and historical plan without inventing completion', () => {
  const before = JSON.stringify(result)
  const state = projectWorkbench([], result, false, 'failed')
  assert.deepEqual(state.steps.map(step => statusLabels[step.status]), [
    '任务已结束，步骤结果未确认', '历史记录：等待执行', '步骤检查通过', '发现问题',
  ])
  assert.equal(JSON.stringify(result), before)
})

test('terminal statuses preserve accepted and challenged evidence without claiming pending steps finished', () => {
  for (const status of ['canceled', 'cancelled', 'partial', 'incomplete', 'budget_exhausted', 'succeeded', 'completed']) {
    assert.deepEqual(projectWorkbench([], result, false, status).steps.map(step => step.status),
      ['ended_unconfirmed', 'historical_pending', 'pass', 'challenged'], status)
  }
  const completed = { solver: { state_revision: 2, progress: { steps: [
    { label: 'S1', verdict: 'ACCEPT', valid: true, current: true },
    { label: 'S2', verdict: 'ACCEPT', valid: true },
  ] } } }
  assert.deepEqual(projectWorkbench([], completed, false, 'succeeded').steps.map(step => step.status), ['pass', 'pass'])
})

test('replay shows historical in-flight snapshot and never borrows the eventual Job result', () => {
  const events = [{ id: 1, event: 'solver_progress', data: { solver_revision: 1, solver: { progress } } }]
  assert.deepEqual(projectWorkbench(events, null, true).steps.map(step => step.status),
    ['historical_active', 'historical_pending', 'pass', 'challenged'])
  assert.equal(projectWorkbench(events, null, false, 'running').steps[0]?.status, 'active')
})

test('unknown public status and faithful needs-review phase keep unresolved steps unknown', () => {
  for (const status of ['unknown', 'needs_review', 'unknown_outcome']) {
    assert.deepEqual(projectWorkbench([], result, false, status).steps.map(step => step.status),
      ['unknown', 'pending', 'pass', 'challenged'])
  }
  assert.equal(projectWorkbench([], { ...result, faithful: { phase: 'needs_review' } }, false, 'running').steps[0]?.status, 'unknown')
  assert.equal(projectWorkbench([], result, false, 'future_status').steps[0]?.status, 'active')
})

test('live running and missing status retain recorded plan and terminal jobs without plans stay empty', () => {
  for (const status of ['running', 'queued', '']) {
    assert.deepEqual(projectWorkbench([], result, false, status).steps.map(step => step.status), ['active', 'pending', 'pass', 'challenged'])
  }
  assert.deepEqual(projectWorkbench([], null, false, 'failed').steps, [])
})
