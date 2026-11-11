import assert from 'node:assert/strict'
import test from 'node:test'
import { createServer } from 'vite'
import { goalCacheResponseSchema } from '../src/api/goal-cache.schemas.ts'

const response = {
  success: true,
  authority: 'metadata_only',
  enabled: false,
  entries: [{ cache_id: 'cache-1', state: 'invalidated', reason: 'cache_cleared', created_at: '2026-11-10T01:00:00Z', updated_at: '2026-11-10T02:00:00Z', source_run_id: 'run-1', source_attempt_id: 'attempt-1', source_grade: 'L2', grade_ceiling: 'L2' }],
  events: [{ cache_id: 'cache-1', event: 'receipt_invalidated', details: { reason: 'cache_cleared', tombstone: true }, created_at: '2026-11-10T02:00:00Z' }, { event: 'cache_cleared', details: { tombstone: true }, created_at: '2026-11-10T02:00:01Z' }],
}

test('goal-cache schema validates metadata and preserves only supplied optional provenance', () => {
  const parsed = goalCacheResponseSchema.parse(response)
  assert.equal(parsed.authority, 'metadata_only')
  assert.equal(parsed.entries[0]?.state, 'invalidated')
  assert.equal(parsed.entries[0]?.source_run_id, 'run-1')
  assert.equal(parsed.entries[0]?.source_grade, 'L2')
  assert.equal(parsed.entries[0]?.reason, 'cache_cleared')
  assert.equal(parsed.events[0]?.details?.reason, 'cache_cleared')
  assert.equal(parsed.entries[0]?.grade_ceiling, 'L2')
  assert.throws(() => goalCacheResponseSchema.parse({ ...response, authority: 'proof' }))
  assert.throws(() => goalCacheResponseSchema.parse({ ...response, entries: [{ ...response.entries[0], state: 'tombstone' }] }))
})

test('goal-cache API uses encoded session paths and CSRF for both mutation methods', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  const originalFetch = globalThis.fetch
  const calls: Array<{ url: string; method: string; csrf: string | null; body: string | null }> = []
  try {
    const { api, setCsrfToken } = await server.ssrLoadModule('/src/api/client.ts')
    setCsrfToken('csrf-test')
    globalThis.fetch = async (input, init) => {
      calls.push({
        url: String(input),
        method: init?.method ?? 'GET',
        csrf: new Headers(init?.headers).get('X-CSRF-Token'),
        body: typeof init?.body === 'string' ? init.body : null,
      })
      return new Response(JSON.stringify(calls.at(-1)?.method === 'GET' ? response : { success: true }), { status: 200 })
    }
    await api.goalCache('session/a ?')
    await api.setGoalCacheEnabled('session/a ?', true)
    await api.clearGoalCache('session/a ?')
    assert.deepEqual(calls, [
      { url: '/api/sessions/session%2Fa%20%3F/goal-cache', method: 'GET', csrf: null, body: null },
      { url: '/api/sessions/session%2Fa%20%3F/goal-cache', method: 'PUT', csrf: 'csrf-test', body: '{"enabled":true}' },
      { url: '/api/sessions/session%2Fa%20%3F/goal-cache', method: 'DELETE', csrf: 'csrf-test', body: null },
    ])
  } finally {
    globalThis.fetch = originalFetch
    await server.close()
  }
})

test('goal-cache 404 remains a typed unavailable response', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  const originalFetch = globalThis.fetch
  try {
    const { api } = await server.ssrLoadModule('/src/api/client.ts')
    globalThis.fetch = async () => new Response(JSON.stringify({ error: 'Not found' }), { status: 404 })
    await assert.rejects(api.goalCache('session-1'), (error: unknown) =>
      (error as { name?: string; status?: number })?.name === 'ApiError' &&
      (error as { status?: number }).status === 404)
  } finally {
    globalThis.fetch = originalFetch
    await server.close()
  }
})
