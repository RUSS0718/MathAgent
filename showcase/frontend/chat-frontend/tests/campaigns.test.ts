import assert from 'node:assert/strict'
import test from 'node:test'
import { campaignSchema } from '../src/api/campaigns.schemas.ts'
import { readDashboardRoute } from '../src/runtime/navigation/app-route.ts'

test('persistent campaign retains incomplete arms and unknown consumption', () => {
  const arm = { status: 'unknown', job_id: null, quality: { status: 'unknown' }, usage: { http_attempts: null, unknown_attempts: null }, cost: null }
  const campaign = campaignSchema.parse({ campaign_id: 'campaign_1', mode: 'fake', status: 'incomplete', common_hash: 'hash', pairs: [{ pair_id: 'p1', problem_hash: 'hash', arms: { baseline: arm, candidate: { ...arm, status: 'failed', error: 'timeout' } } }] })
  assert.equal(campaign.pairs[0].arms.baseline.usage.http_attempts, null)
  assert.equal(campaign.pairs[0].arms.candidate.error, 'timeout')
  assert.equal(campaign.pairs.length, 1)
  assert.throws(() => campaignSchema.parse({ ...campaign, mode: 'pretend-live' }))
})
test('campaign and child Run have stable dashboard deep links', () => {
  assert.equal(readDashboardRoute('/dashboard/campaigns').view, 'campaigns')
  assert.equal(readDashboardRoute('/dashboard/run/job_123').view, 'run')
  assert.equal(readDashboardRoute('/dashboard/run/job_123').runId, 'job_123')
})

test('campaign export preserves public provenance and child evidence fields', () => {
  const arm = { status: 'succeeded', job_id: 'run_1', quality: { status: 'unknown' }, usage: { http_attempts: 1, unknown_attempts: 1 }, cost: null, request_attempts: [{ attempt_id: 'a1', usage: { total_tokens: null } }], budget: { http_attempts: 1 }, artifacts: [{ sha256: 'evidence-hash' }], evidence_hash: 'evidence-hash', run_hash: 'run-hash', events_hash: 'events-hash', strategy_hash: 'strategy-hash', report_url: '/api/agent/jobs/run_1/report' }
  const publicReport = { campaign_id: 'campaign_1', mode: 'fake', status: 'completed', common_hash: 'hash', common: { dataset_version: 'public-toy' }, source: { commit: 'commit-hash' }, config_archive: { sha256: 'config-hash' }, pairs: [{ pair_id: 'p1', problem_hash: 'hash', arms: { baseline: arm, candidate: arm } }], archive: { path: 'report.json', sha256: 'report-hash' } }
  assert.deepEqual(JSON.parse(JSON.stringify(campaignSchema.parse(publicReport))), publicReport)
})
