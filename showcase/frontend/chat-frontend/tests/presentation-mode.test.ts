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
