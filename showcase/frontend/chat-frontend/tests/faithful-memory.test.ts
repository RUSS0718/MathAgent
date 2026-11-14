import assert from 'node:assert/strict'
import test from 'node:test'
import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import {
  populationMemoryResponseSchema,
  populationMemoryControlResponseSchema,
  populationMemoryUpdateResponseSchema,
  runMemoryResponseSchema,
} from '../src/api/memory.schemas.ts'

const runMemory = runMemoryResponseSchema.parse({
  success: true,
  run_memory: {
    run_id: 'run_current',
    source: 'persisted_state',
    state_revision: 12,
    phase: 'TERMINAL',
    status: 'completed',
    plan_version: 3,
    graph_version: 7,
    budget: { http_attempts: 2 },
    valid_evidence: [{ result_id: 'evidence_1', evidence_level: 'L1', category: 'Lemma' }],
    invalidated_count: 1,
  },
})

const memoryUsage = [
  { call_id: 'call-public-1', record_ids: ['memory-adopt', 'memory-reject'], decision_status: 'reported', decisions: [
    { record_id: 'memory-adopt', decision: 'adopt', reason: '适用当前问题' },
    { record_id: 'memory-reject', decision: 'reject', reason: '条件不适用' },
  ] },
  { call_id: 'call-public-2', record_ids: ['memory-injected-only'], decision_status: 'not_reported', decisions: [] },
] as const

test('memory usage defaults to empty and validates public decisions and bounded reasons', () => {
  assert.deepEqual(runMemory.run_memory.memory_usage, [])
  const parseUsage = (memory_usage: unknown) => runMemoryResponseSchema.safeParse({ ...runMemory, run_memory: { ...runMemory.run_memory, memory_usage } })
  assert.equal(parseUsage(memoryUsage).success, true)
  assert.equal(parseUsage([{ ...memoryUsage[0], decision_status: 'adopted' }]).success, false)
  assert.equal(parseUsage([{ ...memoryUsage[0], decisions: [{ record_id: 'record', decision: 'verified', reason: '' }] }]).success, false)
  assert.equal(parseUsage([{ ...memoryUsage[0], decisions: [{ record_id: 'record', decision: 'adopt', reason: 'x'.repeat(501) }] }]).success, false)
})

test('memory usage shows adoption, rejection and unreported injection separately', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const { default: FaithfulMemorySection } = await server.ssrLoadModule('/src/components/FaithfulMemorySection.vue')
    const html = await renderToString(createSSRApp(FaithfulMemorySection, {
      runMemory: { status: 'available', data: runMemoryResponseSchema.parse({ ...runMemory, run_memory: { ...runMemory.run_memory, memory_usage: memoryUsage } }) },
      populationMemory: { status: 'unavailable' }, populationMemoryControl: { status: 'unavailable' },
    }))
    assert.match(html, /检索\/注入记录/)
    assert.match(html, /memory-adopt · 明确采用（adopt） · 原因：适用当前问题/)
    assert.match(html, /memory-reject · 明确拒绝（reject） · 原因：条件不适用/)
    assert.match(html, /memory-injected-only/)
    assert.match(html, /未报告采用或拒绝（not_reported）/)
    assert.match(html, /检索或注入不表示采用/)
    assert.doesNotMatch(html, /memory-injected-only · 明确采用/)
  } finally { await server.close() }
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

const populationMemoryControl = populationMemoryControlResponseSchema.parse({
  success: true,
  authority: 'observations_only',
  injection_enabled: true,
  observations: [{
    record_id: 'population-record-1',
    observation: {
    outcome: 'failure',
    applicability: { domain: 'algebra' },
      versions: { graph: 4, plan: 2 },
      cost: { attempts: 3 },
    content: { route_summary: '不得显示的观察内容' },
    },
    provenance: { source_run: 'run_previous' },
    authority: 'historical_observation',
    trust: 'advisory',
  }],
})

test('population memory schemas accept both history and control contracts', () => {
  assert.equal(populationMemoryControl.injection_enabled, true)
  assert.equal(populationMemoryControl.observations[0].trust, 'advisory')
  assert.equal(populationMemoryUpdateResponseSchema.parse({
    success: true,
    enabled: false,
    injection_enabled: false,
  }).injection_enabled, false)
  assert.equal(populationMemoryControlResponseSchema.safeParse({
    ...populationMemoryControl,
    observations: [{ ...populationMemoryControl.observations[0], trust: 'verified' }],
  }).success, false)
  assert.equal(populationMemoryControlResponseSchema.safeParse({
    ...populationMemoryControl,
    observations: [{ ...populationMemoryControl.observations[0], observation: { outcome: 'stopped' } }],
  }).success, false)
  assert.equal(populationMemoryUpdateResponseSchema.safeParse({ success: true, enabled: 'false', injection_enabled: false }).success, false)
})

test('run memory schema uses the public result ID, level, and category fields', () => {
  assert.equal(runMemory.run_memory.valid_evidence[0]?.result_id, 'evidence_1')
  assert.equal(runMemory.run_memory.valid_evidence[0]?.evidence_level, 'L1')
  assert.equal(runMemory.run_memory.valid_evidence[0]?.category, 'Lemma')
  assert.equal(runMemoryResponseSchema.safeParse({
    success: true,
    run_memory: { ...runMemory.run_memory, valid_evidence: 'not-an-array' },
  }).success, false)
})

test('memory API uses session-scoped GET and PUT paths, CSRF, and validates responses', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  const originalFetch = globalThis.fetch
  const calls: Array<{ url: string; method: string; body?: string; csrf?: string; credentials?: RequestCredentials }> = []
  const responses = [
    runMemory,
    populationMemory,
    populationMemoryControl,
    { success: true, enabled: false, injection_enabled: false },
  ]
  try {
    const { api, setCsrfToken } = await server.ssrLoadModule('/src/api/client.ts')
    setCsrfToken('csrf-test')
    globalThis.fetch = async (input, init) => {
      const headers = new Headers(init?.headers)
      calls.push({
        url: String(input),
        method: init?.method ?? 'GET',
        body: typeof init?.body === 'string' ? init.body : undefined,
        csrf: headers.get('X-CSRF-Token') ?? undefined,
        credentials: init?.credentials,
      })
      return new Response(JSON.stringify(responses[calls.length - 1]), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }
    await api.runMemory('job/a')
    const history = await api.populationMemory('session ?')
    const loaded = await api.populationMemoryControl('session ?')
    await api.setPopulationMemoryInjection('session ?', false)
    assert.equal(loaded.sessionId, 'session ?')
    assert.equal(history.observations[0].source_run_id, 'run_previous')
    assert.deepEqual(calls, [
      { url: '/api/agent/jobs/job%2Fa/memory', method: 'GET', body: undefined, csrf: undefined, credentials: 'same-origin' },
      { url: '/api/sessions/session%20%3F/population-memory', method: 'GET', body: undefined, csrf: undefined, credentials: 'same-origin' },
      { url: '/api/sessions/session%20%3F/memory/population/session%20%3F', method: 'GET', body: undefined, csrf: undefined, credentials: 'same-origin' },
      {
        url: '/api/sessions/session%20%3F/memory/population/session%20%3F/injection',
        method: 'PUT',
        body: '{"enabled":false}',
        csrf: 'csrf-test',
        credentials: 'same-origin',
      },
    ])

    globalThis.fetch = async () => new Response(JSON.stringify({ success: true, enabled: 'no', injection_enabled: false }), { status: 200 })
    await assert.rejects(api.setPopulationMemoryInjection('session ?', false), (error: unknown) =>
      (error as { code?: string })?.code === 'invalid_response')
  } finally {
    globalThis.fetch = originalFetch
    const { setCsrfToken } = await server.ssrLoadModule('/src/api/client.ts')
    setCsrfToken('')
    await server.close()
  }
})

test('404 from population memory is preserved as unavailable', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  const originalFetch = globalThis.fetch
  try {
    const { api } = await server.ssrLoadModule('/src/api/client.ts')
    let requests = 0
    globalThis.fetch = async () => {
      requests += 1
      return new Response(JSON.stringify({ error: 'Not found' }), { status: 404 })
    }
    await assert.rejects(api.populationMemoryControl('session_1'), (error: unknown) =>
      (error as { name?: string; status?: number })?.name === 'ApiError' && (error as { status?: number }).status === 404)
    await assert.rejects(api.populationMemoryControl(''), (error: unknown) =>
      (error as { name?: string; status?: number })?.name === 'ApiError' && (error as { status?: number }).status === 404)
    await assert.rejects(api.setPopulationMemoryInjection('', true), (error: unknown) =>
      (error as { name?: string; status?: number })?.name === 'ApiError' && (error as { status?: number }).status === 404)
    assert.equal(requests, 1)
  } finally {
    globalThis.fetch = originalFetch
    await server.close()
  }
})

test('memory import and clear reuse scoped management API, CSRF and response validation', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  const originalFetch = globalThis.fetch
  try {
    const { api, setCsrfToken } = await server.ssrLoadModule('/src/api/client.ts')
    setCsrfToken('csrf-memory')
    const calls: Array<{ url: string; method?: string; body: unknown; csrf: string | null }> = []
    globalThis.fetch = async (input, init) => {
      calls.push({ url: String(input), method: init?.method, body: init?.body ? JSON.parse(String(init.body)) : null, csrf: new Headers(init?.headers).get('X-CSRF-Token') })
      return new Response(JSON.stringify(init?.method === 'DELETE'
        ? { success: true, cleared: true }
        : { success: true, record_id: 'imported', authority: 'advisory' }), { status: 200 })
    }
    await api.importPopulationMemory('target ?', 'source /', 'record-1')
    await api.clearPopulationMemory('target ?')
    assert.deepEqual(calls, [
      { url: '/api/sessions/target%20%3F/memory/population/target%20%3F/imports', method: 'POST', body: { source_session_id: 'source /', source_kind: 'population', source_scope_id: 'source /', record_id: 'record-1' }, csrf: 'csrf-memory' },
      { url: '/api/sessions/target%20%3F/memory/population/target%20%3F', method: 'DELETE', body: null, csrf: 'csrf-memory' },
    ])
    globalThis.fetch = async () => new Response(JSON.stringify({ success: true, cleared: false }), { status: 200 })
    await assert.rejects(api.clearPopulationMemory('target'), (error: unknown) => (error as { code?: string }).code === 'invalid_response')
    globalThis.fetch = async () => new Response(JSON.stringify({ error: 'forbidden' }), { status: 403 })
    await assert.rejects(api.importPopulationMemory('target', 'other-owner', 'record'), (error: unknown) => (error as { status?: number }).status === 403)
    setCsrfToken('')
  } finally {
    globalThis.fetch = originalFetch
    await server.close()
  }
})

test('memory section displays advisory fields and reflects enabled or disabled injection state', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const { default: FaithfulMemorySection } = await server.ssrLoadModule('/src/components/FaithfulMemorySection.vue')
    const html = await renderToString(createSSRApp(FaithfulMemorySection, {
      runMemory: { status: 'available', data: runMemory },
      populationMemory: { status: 'available', data: populationMemory },
      populationMemoryControl: { status: 'available', data: { ...populationMemoryControl, sessionId: 'session_1' } },
    }))
    assert.match(html, /会话记忆观察/)
    assert.match(html, /启用此会话的 Population Memory 注入/)
    assert.match(html, /记录终态 Run 的观察/)
    assert.match(html, /type="checkbox"[^>]*checked/)
    assert.match(html, /结果观察/)
    assert.match(html, /适用范围/)
    assert.match(html, /版本/)
    assert.match(html, /成本观察/)
    assert.match(html, /来源记录/)
    assert.doesNotMatch(html, /population-record-1|不得显示的观察内容/)
    assert.match(html, /persisted_state/)
    assert.match(html, /run_current/)
    assert.match(html, /evidence_1 · 等级：L1 · 类别：Lemma/)

    const disabledHtml = await renderToString(createSSRApp(FaithfulMemorySection, {
      runMemory: { status: 'unavailable' },
      populationMemory: { status: 'available', data: populationMemory },
      populationMemoryControl: { status: 'available', data: { ...populationMemoryControl, injection_enabled: false, sessionId: 'session_1' } },
    }))
    assert.match(disabledHtml, /type="checkbox"(?![^>]*checked)/)

    const historyErrorHtml = await renderToString(createSSRApp(FaithfulMemorySection, {
      runMemory: { status: 'unavailable' },
      populationMemory: { status: 'error' },
      populationMemoryControl: { status: 'available', data: { ...populationMemoryControl, sessionId: 'session_1' } },
    }))
    assert.match(historyErrorHtml, /历史路线观察暂时无法读取/)
  } finally {
    await server.close()
  }
})

test('controls stay unavailable without session identity or population memory', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const { default: FaithfulMemorySection } = await server.ssrLoadModule('/src/components/FaithfulMemorySection.vue')
    const noSessionHtml = await renderToString(createSSRApp(FaithfulMemorySection, {
      runMemory: { status: 'unavailable' },
      populationMemory: { status: 'available', data: populationMemory },
      populationMemoryControl: { status: 'available', data: populationMemoryControl },
    }))
    assert.doesNotMatch(noSessionHtml, /type="checkbox"/)
    assert.match(noSessionHtml, /注入控制不可用/)

    const unavailableHtml = await renderToString(createSSRApp(FaithfulMemorySection, {
      runMemory: { status: 'unavailable' },
      populationMemory: { status: 'unavailable' },
      populationMemoryControl: { status: 'unavailable' },
    }))
    assert.doesNotMatch(unavailableHtml, /<section/)
  } finally {
    await server.close()
  }
})
