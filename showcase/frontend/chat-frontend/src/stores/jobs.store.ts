import { defineStore } from 'pinia'
import type { DecodedSseEvent } from '../api/events.schemas'
import type { ActiveJobResponse } from '../api/jobs.schemas'

type Status = 'queued' | 'running' | 'waiting_input' | 'succeeded' | 'failed' | 'canceled'
export interface JobRecord {
  jobId: string
  sessionId: string
  status: Status
  lastEventId: number
  renderedEventId: number
  summary: string
  error: string | null
  events: DecodedSseEvent[]
}

const terminalStatuses = new Set<Status>(['succeeded', 'failed', 'canceled'])

export const useJobsStore = defineStore('jobs', {
  state: () => ({ records: {} as Record<string, JobRecord> }),
  getters: {
    byId: (state) => (id: string) => state.records[id],
    activeForSession: (state) => (sessionId: string) => Object.values(state.records).find(
      (job) => job.sessionId === sessionId && ['queued', 'running', 'waiting_input'].includes(job.status),
    ),
  },
  actions: {
    start(jobId: string, sessionId: string, status: Status, lastEventId = 0): JobRecord {
      const record = this.records[jobId] ?? {
        jobId,
        sessionId,
        status,
        lastEventId,
        renderedEventId: 0,
        summary: '',
        error: null,
        events: [],
      }
      record.sessionId = sessionId
      if (!terminalStatuses.has(record.status)) record.status = status
      record.lastEventId = Math.max(record.lastEventId, lastEventId)
      this.records[jobId] = record
      return record
    },
    observe(job: ActiveJobResponse): JobRecord {
      const existing = this.records[job.job_id]
      const cursor = existing?.events.length ? job.last_event_id ?? 0 : 0
      const record = this.start(job.job_id, job.session_id, job.status, cursor)
      record.error = typeof job.error === 'string' ? job.error : null
      return record
    },
    applyEvent(jobId: string, event: DecodedSseEvent): void {
      const record = this.records[jobId]
      if (!record || event.id === null || event.id <= record.lastEventId) return
      record.lastEventId = event.id
      if (event.event !== 'heartbeat') record.events.push(event)
      const type = event.data.type
      const terminal = terminalStatuses.has(record.status)
      if (!terminal && type === 'queued') record.status = 'queued'
      else if (!terminal && type === 'resumed') record.status = 'queued'
      else if (!terminal && type === 'running') record.status = 'running'
      else if (!terminal && type === 'interrupt') record.status = 'waiting_input'
      else if (!terminal && type === 'final_result') record.status = 'succeeded'
      else if (!terminal && (type === 'error' || type === 'timeout' || type === 'needs_review')) {
        record.status = 'failed'
        record.error = typeof event.data.message === 'string' ? event.data.message : type === 'timeout' ? 'run_deadline_exhausted' : type === 'needs_review' ? 'needs_review' : 'job_failed'
      } else if (!terminal && type === 'canceled') {
        record.status = 'canceled'
        record.error = typeof event.data.message === 'string' ? event.data.message : 'job_canceled'
      }
      if (type !== 'heartbeat') record.renderedEventId = event.id
      const result = event.data.data
      if (result && typeof result === 'object' && 'summary' in result) {
        record.summary = String(result.summary)
      } else if (typeof event.data.summary === 'string') {
        record.summary = event.data.summary
      }
    },
    setStreamError(jobId: string, message: string): void {
      const record = this.records[jobId]
      if (record) record.error = message
    },
    reset(): void {
      this.records = {}
    },
  },
})

