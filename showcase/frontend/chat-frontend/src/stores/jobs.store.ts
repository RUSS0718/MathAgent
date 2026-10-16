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
      }
      record.sessionId = sessionId
      if (!terminalStatuses.has(record.status)) record.status = status
      record.lastEventId = Math.max(record.lastEventId, lastEventId)
      this.records[jobId] = record
      return record
    },
    observe(job: ActiveJobResponse): JobRecord {
      return this.start(job.job_id, job.session_id, job.status, job.last_event_id ?? 0)
    },
    applyEvent(jobId: string, event: DecodedSseEvent): void {
      const record = this.records[jobId]
      if (!record || event.id === null || event.id <= record.lastEventId) return
      record.lastEventId = event.id
      const type = event.data.type
      const terminal = terminalStatuses.has(record.status)
      if (!terminal && type === 'queued') record.status = 'queued'
      else if (!terminal && type === 'resumed') record.status = 'queued'
      else if (!terminal && type === 'running') record.status = 'running'
      else if (!terminal && type === 'interrupt') record.status = 'waiting_input'
      else if (!terminal && type === 'final_result') record.status = 'succeeded'
      else if (!terminal && type === 'error') {
        record.status = 'failed'
        record.error = typeof event.data.message === 'string' ? event.data.message : 'job_failed'
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
