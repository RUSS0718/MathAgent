import assert from 'node:assert/strict'
import test from 'node:test'
import { createPinia, setActivePinia } from 'pinia'
import { useJobsStore } from '../src/stores/jobs.store.ts'

test('snapshot refresh keeps last consumed event cursor across disconnect', () => {
  setActivePinia(createPinia())
  const jobs = useJobsStore()
  jobs.start('run_1', 'session_1', 'running')
  jobs.applyEvent('run_1', { id: 10, event: 'progress', data: { type: 'progress', summary: 'observed' } })
  jobs.observe({ job_id: 'run_1', session_id: 'session_1', status: 'running', last_event_id: 20 })
  assert.equal(jobs.byId('run_1')?.lastEventId, 10)
  jobs.applyEvent('run_1', { id: 11, event: 'progress', data: { type: 'progress', summary: 'recovered' } })
  assert.equal(jobs.byId('run_1')?.events.at(-1)?.data.summary, 'recovered')
})

test('explicit confirmed resume opens a new generation while stale terminal events stay ignored', () => {
  setActivePinia(createPinia())
  const jobs = useJobsStore()
  jobs.start('run_1', 'session_1', 'running')
  jobs.applyEvent('run_1', { id: 10, event: 'needs_review', data: { type: 'needs_review' } })
  jobs.confirmResume('run_1')
  jobs.applyEvent('run_1', { id: 10, event: 'error', data: { type: 'error' } })
  jobs.applyEvent('run_1', { id: 11, event: 'resumed', data: { type: 'resumed' } })
  jobs.applyEvent('run_1', { id: 12, event: 'running', data: { type: 'running' } })
  assert.equal(jobs.byId('run_1')?.status, 'running')
})
