import assert from 'node:assert/strict'
import test from 'node:test'
import { parsePresentationInput } from '../src/runtime/presentation/mode.ts'

test('parses explicit output commands without changing the math problem', () => {
  assert.deepEqual(parsePresentationInput('/teach  1+1=2'), {
    problem: '1+1=2', presentationMode: 'teach',
  })
  assert.deepEqual(parsePresentationInput('/report\n证明 1+1=2'), {
    problem: '证明 1+1=2', presentationMode: 'report',
  })
})

test('keeps ordinary text on the legacy submission path', () => {
  assert.deepEqual(parsePresentationInput('求解 /teach 的含义'), {
    problem: '求解 /teach 的含义',
  })
  assert.deepEqual(parsePresentationInput('/teach'), {
    problem: '', presentationMode: 'teach',
  })
})

import { presentationArtifactSchema } from '../src/api/presentation.schemas.ts'
test('output request accepts legacy zero and bounded one call while forbidding solver resume', () => {
  const schema = presentationArtifactSchema.shape.output_request.unwrap()
  const request = { id: 'output:test', kind: 'presentation_only', solver_resumed: false }
  for (const model_calls of [0, 1]) assert.equal(schema.safeParse({ ...request, model_calls }).success, true)
  for (const model_calls of [-1, 2, 1.5]) assert.equal(schema.safeParse({ ...request, model_calls }).success, false)
  assert.equal(schema.safeParse({ ...request, model_calls: 1, solver_resumed: true }).success, false)
})
