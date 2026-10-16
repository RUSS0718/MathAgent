import { isTerminalEvent, SseProtocolError, type DecodedSseEvent } from '../../api/events.schemas'
import { SseTransportError, readJobEvents } from './sse-transport'
import { useJobsStore } from '../../stores/jobs.store'

export class JobController {
  private generation = 0
  private activeAbort: AbortController | null = null

  constructor(private readonly jobs: ReturnType<typeof useJobsStore>) {}

  async subscribe(jobId: string): Promise<void> {
    const generation = ++this.generation
    this.activeAbort?.abort()
    const abort = new AbortController()
    this.activeAbort = abort
    const record = this.jobs.byId(jobId)
    if (!record) return
    try {
      await readJobEvents(jobId, record.lastEventId, {
        signal: abort.signal,
        onEvent: (event: DecodedSseEvent) => {
          if (generation !== this.generation || abort.signal.aborted) return
          this.jobs.applyEvent(jobId, event)
          if (isTerminalEvent(event)) abort.abort()
        },
      })
    } catch (error) {
      if (generation !== this.generation || abort.signal.aborted) return
      if (error instanceof SseProtocolError) this.jobs.setStreamError(jobId, error.code)
      else if (error instanceof SseTransportError) this.jobs.setStreamError(jobId, error.code)
      else this.jobs.setStreamError(jobId, 'events_stream_error')
    }
  }

  stopAll(): void {
    this.generation += 1
    this.activeAbort?.abort()
    this.activeAbort = null
  }
}
