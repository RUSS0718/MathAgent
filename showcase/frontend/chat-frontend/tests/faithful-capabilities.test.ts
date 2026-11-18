import assert from 'node:assert/strict'
import test from 'node:test'
import { capabilitiesResponseSchema } from '../src/api/capabilities.schemas.ts'

const base = {
  profile: 'showcase', jobs: { enabled: true, status: 'available' },
  sse: { enabled: true, status: 'available' }, verification_mode: ['auto'],
  files: { upload: { enabled: false } },
  capabilities: { jobs: true, sse: true, verification_mode: ['auto'], file_upload: { enabled: false } },
}
const faithful = { enabled: true, ready: true, solver_mode: 'star_reference', input_mode: 'automatic', unavailable_reasons: [] }

test('capabilities preserves the frozen Faithful automatic entry contract', () => {
  assert.deepEqual(capabilitiesResponseSchema.parse({ ...base, faithful }).faithful, faithful)
})
test('capabilities preserves unavailable reasons without requiring readiness', () => {
  const unavailable = { ...faithful, ready: false, unavailable_reasons: ['python_image_missing'] }
  assert.deepEqual(capabilitiesResponseSchema.parse({ ...base, faithful: unavailable }).faithful, unavailable)
})
test('old services can omit the Faithful entry', () => {
  assert.equal(capabilitiesResponseSchema.parse(base).faithful, undefined)
})
test('capabilities retains maturity and optional limitations for the ordinary entry', () => {
  const expanded = { ...faithful, version: 'faithful-capabilities-v1', maturity: 'experimental',
    features: { auto_problem_spec: true }, optional_limitations: ['formal_not_configured'] }
  assert.deepEqual(capabilitiesResponseSchema.parse({ ...base, faithful: expanded }).faithful, expanded)
})
test('Faithful entry rejects a different solver or input contract', () => {
  for (const invalid of [{ ...faithful, solver_mode: 'legacy' }, { ...faithful, input_mode: 'manual' }]) {
    assert.equal(capabilitiesResponseSchema.safeParse({ ...base, faithful: invalid }).success, false)
  }
})
