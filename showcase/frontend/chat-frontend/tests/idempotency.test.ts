import test from 'node:test'
import assert from 'node:assert/strict'
import { createIdempotencyKey } from '../src/runtime/jobs/idempotency.ts'

test('creates UUID v4 idempotency keys', () => {
  const key = createIdempotencyKey()
  assert.match(key, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
})
