import assert from 'node:assert/strict'
import test from 'node:test'
import { readDashboardRoute } from '../src/runtime/navigation/app-route.ts'
import { buildSystemDeepLink, parseSystemDeepLink } from '../src/runtime/navigation/system-deeplink.ts'

test('the default frontend build keeps the F7 route disabled', () => {
  assert.equal(readDashboardRoute('/dashboard/system').view, 'workspace')
})

test('builds and restores the immutable v1 Run/output/artifact/paragraph link', () => {
  const state = {
    runId: 'run_abc-123',
    mode: 'teach' as const,
    outputId: 'output:abc123',
    artifactId: 'presentation:def456',
    paragraphId: 'paragraph:12',
    graphVersion: 3,
    nodeId: 'p2',
  }
  const href = buildSystemDeepLink(state)
  assert.match(href, /^\/dashboard\/system\?scheme=f7-deeplink-v1&run=/)
  const parsed = parseSystemDeepLink('/dashboard/system', new URL(href, 'http://localhost').search)
  assert.deepEqual(parsed, { kind: 'valid', state })
})

test('does not reinterpret unknown scheme or a malformed Run identity', () => {
  assert.deepEqual(parseSystemDeepLink('/dashboard/system', '?scheme=f7-deeplink-v2&run=run_a'),
    { kind: 'invalid', reason: 'scheme_unsupported' })
  assert.deepEqual(parseSystemDeepLink('/dashboard/system', '?scheme=f7-deeplink-v1&run=bad%20run'),
    { kind: 'invalid', reason: 'run_id_invalid' })
})

test('does not treat other dashboard routes as F7 deep links', () => {
  assert.deepEqual(parseSystemDeepLink('/dashboard/run/run_a', '?scheme=f7-deeplink-v1&run=run_a'),
    { kind: 'not_system' })
})

test('rejects partial output identity and paragraph anchors without an artifact identity', () => {
  assert.throws(() => buildSystemDeepLink({ runId: 'run_a', outputId: 'output:one' }), /presentation_identity_incomplete/)
  assert.throws(() => buildSystemDeepLink({ runId: 'run_a', paragraphId: 'paragraph:1' }), /paragraph_identity_invalid/)
  assert.deepEqual(parseSystemDeepLink('/dashboard/system',
    '?scheme=f7-deeplink-v1&run=run_a&node=p1'),
  { kind: 'invalid', reason: 'node_identity_invalid' })
})

test('keeps the Run available when an incoming link has only half an output identity', () => {
  assert.deepEqual(parseSystemDeepLink('/dashboard/system',
    '?scheme=f7-deeplink-v1&run=run_a&output=output:one&paragraph=paragraph:2'),
  { kind: 'valid', state: { runId: 'run_a' }, unavailableReason: 'presentation_identity_incomplete' })
  assert.deepEqual(parseSystemDeepLink('/dashboard/system',
    '?scheme=f7-deeplink-v1&run=run_a&artifact=presentation:one'),
  { kind: 'valid', state: { runId: 'run_a' }, unavailableReason: 'presentation_identity_incomplete' })
})
