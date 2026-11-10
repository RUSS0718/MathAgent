import assert from 'node:assert/strict'
import test from 'node:test'
import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { populationMemoryResponseSchema, runMemoryResponseSchema } from '../src/api/memory.schemas.ts'

const runMemory = runMemoryResponseSchema.parse({
  success: true,
  run_memory: {
    run_id: 'run_current',
    source: 'authoritative_run_snapshot',
    state_revision: 12,
    phase: 'TERMINAL',
    status: 'completed',
    plan_version: 3,
    graph_version: 7,
    budget: { http_attempts: 2 },
    valid_evidence: [{ result_id: 'evidence_1', evidence_level: 'llm_reviewed', category: 'Lemma' }],
    invalidated_count: 1,
  },
})

const populationMemory = populationMemoryResponseSchema.parse({
  success: true,
  authority: 'observations_only',
  observations: [{
    source_run_id: 'run_previous',
    source_state_revision: 5,
    route_id: 'route_2',
    parent_route_id: null,
    status: 'stopped',
    stop_reason: null,
    graph_version: 4,
    plan_version: 2,
    policy_version: 1,
    unknown_observation_count: 0,
  }],
  total_jobs: 1,
  limit: 20,
  offset: 0,
})

test('memory API methods use read-only opt-in paths and validate their contracts', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  const originalFetch = globalThis.fetch
  const calls: Array<{ url: string; method: string }> = []
  try {
    const { api } = await server.ssrLoadModule('/src/api/client.ts')
    globalThis.fetch = async (input, init) => {
      calls.push({ url: String(input), method: init?.method ?? 'GET' })
      const payload = calls.length === 1 ? runMemory : populationMemory
      return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }
    await api.runMemory('job/a')
    await api.populationMemory('session ?')
    assert.deepEqual(calls, [
      { url: '/api/agent/jobs/job%2Fa/memory', method: 'GET' },
      { url: '/api/sessions/session%20%3F/population-memory', method: 'GET' },
    ])
  } finally {
    globalThis.fetch = originalFetch
    await server.close()
  }
})

test('404 from an opt-in memory endpoint remains a typed unavailable API response', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  const originalFetch = globalThis.fetch
  try {
    const { api } = await server.ssrLoadModule('/src/api/client.ts')
    globalThis.fetch = async () => new Response(JSON.stringify({ error: 'Not found' }), { status: 404 })
    await assert.rejects(api.runMemory('job_1'), (error: unknown) => (error as { name?: string; status?: number })?.name === 'ApiError' && (error as { status?: number }).status === 404)
  } finally {
    globalThis.fetch = originalFetch
    await server.close()
  }
})

test('memory section exposes provenance, evidence grade and observation limits', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const { default: FaithfulMemorySection } = await server.ssrLoadModule('/src/components/FaithfulMemorySection.vue')
    const html = await renderToString(createSSRApp(FaithfulMemorySection, {
      runMemory: { status: 'available', data: runMemory },
      populationMemory: { status: 'available', data: populationMemory },
    }))
    assert.match(html, /运行记忆/)
    assert.match(html, /authoritative_run_snapshot/)
    assert.match(html, /run_current/)
    assert.match(html, /等级：llm_reviewed/)
    assert.match(html, /历史路线观察/)
    assert.match(html, /run_previous/)
    assert.match(html, /未知（未提供）/)
    assert.match(html, /不构成数学证明/)
    assert.match(html, /不表示 verified_gain/)
    assert.doesNotMatch(html, /观察记录.*(证明通过|已验证收益)/)
  } finally {
    await server.close()
  }
})

test('empty and unavailable memory states stay explicit and accessible', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const { default: FaithfulMemorySection } = await server.ssrLoadModule('/src/components/FaithfulMemorySection.vue')
    const emptyRun = runMemoryResponseSchema.parse({
      success: true,
      run_memory: { ...runMemory.run_memory, valid_evidence: [] },
    })
    const emptyHistory = populationMemoryResponseSchema.parse({ ...populationMemory, observations: [], total_jobs: 0 })
    const emptyHtml = await renderToString(createSSRApp(FaithfulMemorySection, {
      runMemory: { status: 'available', data: emptyRun },
      populationMemory: { status: 'available', data: emptyHistory },
    }))
    assert.match(emptyHtml, /当前没有有效证据记录/)
    assert.match(emptyHtml, /没有可显示的历史路线观察/)
    assert.match(emptyHtml, /role="status"/)

    const hiddenHtml = await renderToString(createSSRApp(FaithfulMemorySection, {
      runMemory: { status: 'unavailable' },
      populationMemory: { status: 'unavailable' },
    }))
    assert.doesNotMatch(hiddenHtml, /<section/)
  } finally {
    await server.close()
  }
})
