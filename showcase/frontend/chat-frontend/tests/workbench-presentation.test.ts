import assert from 'node:assert/strict'
import { test } from 'node:test'
import { projectHandoffs } from '../src/runtime/jobs/workbench.ts'

test('whole-solution handoff tone reflects the public verdict independently of summary copy', () => {
  const project = (summary: string, verdict?: string) => projectHandoffs([{
    event: { data: { solver_event_type: 'final_candidate_reviewed', verdict } },
    message: { message_id: 'whole-review', kind: 'decision', summary },
  } as Parameters<typeof projectHandoffs>[0][number]])[0]
  assert.equal(project('整题审查通过').tone, 'handoff')
  assert.equal(project('Review accepted', 'ACCEPT').tone, 'approve')
  assert.equal(project('整题审查通过', 'REJECT').tone, 'handoff')
})
