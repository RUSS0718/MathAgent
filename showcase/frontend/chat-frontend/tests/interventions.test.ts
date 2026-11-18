import assert from 'node:assert/strict'
import test from 'node:test'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createServer } from 'vite'
import { interventionsResponseSchema } from '../src/api/interventions.schemas.ts'

const view = {
  job_id: 'run-demo', status: 'paused', checkpoint_revision: 12,
  failure_sources: [{ source_event_id: 'solver_event_demo', source_state_revision: 9,
    event_type: 'step_reviewed', verdict: 'CHALLENGE', step_label: '步骤 1' }],
  root_obligations: [{ obligation_id: 'root-1', proposition: 'x = 2' }],
  current_method_id: 'direct', hypotheses: [], actions: [], pairs: [], effects: [],
}

test('intervention response schema preserves only the declared public view shape', () => {
  const parsed = interventionsResponseSchema.parse({ success: true, interventions: view })
  assert.equal(parsed.interventions.failure_sources[0]?.source_event_id, 'solver_event_demo')
  assert.equal(parsed.interventions.root_obligations[0]?.obligation_id, 'root-1')
  assert.throws(() => interventionsResponseSchema.parse({
    success: true, interventions: { ...view, status: 7 },
  }))
})

test('intervention API encodes job identity and attaches CSRF to state-changing requests', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  const originalFetch = globalThis.fetch
  const calls: Array<{ url: string; method: string; csrf: string | null }> = []
  try {
    const { api, setCsrfToken } = await server.ssrLoadModule('/src/api/client.ts')
    setCsrfToken('csrf-test')
    globalThis.fetch = async (input, init) => {
      calls.push({ url: String(input), method: init?.method ?? 'GET',
        csrf: new Headers(init?.headers).get('X-CSRF-Token') })
      const result = calls.at(-1)?.method === 'GET'
        ? { success: true, interventions: view }
        : { success: true, job_id: 'run/a', status: 'pause_requested' }
      return new Response(JSON.stringify(result), { status: 200 })
    }
    await api.interventions('run/a')
    await api.requestInterventionPause('run/a')
    assert.deepEqual(calls, [
      { url: '/api/agent/jobs/run%2Fa/interventions', method: 'GET', csrf: null },
      { url: '/api/agent/jobs/run%2Fa/interventions/pause', method: 'POST', csrf: 'csrf-test' },
    ])
  } finally {
    globalThis.fetch = originalFetch
    await server.close()
  }
})

test('intervention setup presents only public failure and obligation choices', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const { default: Setup } = await server.ssrLoadModule('/src/components/FaithfulInterventionSetup.vue')
    const html = await renderToString(createSSRApp(Setup, { jobId: 'run-demo', view }))
    assert.match(html, /登记并预留单动作配对/)
    assert.match(html, /步骤 1 · CHALLENGE/)
    assert.match(html, /x = 2/)
    assert.match(html, /direct/)
    assert.doesNotMatch(html, /checkpoint_json|applied_config_fingerprint/)
  } finally {
    await server.close()
  }
})
