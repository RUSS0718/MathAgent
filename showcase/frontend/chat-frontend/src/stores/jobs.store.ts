import { defineStore } from 'pinia'
import type { DecodedSseEvent } from '../api/events.schemas'
import type { ActiveJobResponse } from '../api/jobs.schemas'

type Status = 'queued' | 'running' | 'waiting_input' | 'succeeded' | 'failed' | 'canceled'
export interface JobRecord { jobId: string; sessionId: string; status: Status; lastEventId: number; summary: string; error: string | null }
export const useJobsStore = defineStore('jobs', {
  state: () => ({ records: {} as Record<string, JobRecord> }),
  getters: { byId: (state) => (id: string) => state.records[id], activeForSession: (state) => (sessionId: string) => Object.values(state.records).find((job) => job.sessionId === sessionId && ['queued', 'running', 'waiting_input'].includes(job.status)) },
  actions: {
    start(jobId: string, sessionId: string, status: Status): JobRecord { const record = this.records[jobId] ?? { jobId, sessionId, status, lastEventId: 0, summary: '', error: null }; record.status = status; this.records[jobId] = record; return record },
    observe(job: ActiveJobResponse): JobRecord { return this.start(job.job_id, job.session_id, job.status) },
    applyEvent(jobId: string, event: DecodedSseEvent): void { const record = this.records[jobId]; if (!record || event.id <= record.lastEventId) return; record.lastEventId = event.id; if (event.data.status === 'succeeded') record.status = 'succeeded'; if (typeof event.data.message === 'string') record.error = event.data.message; if (event.data.data && typeof event.data.data === 'object' && 'summary' in event.data.data) record.summary = String(event.data.data.summary) },
    reset(): void { this.records = {} },
  },
})
