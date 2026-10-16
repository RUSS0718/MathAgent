import { readJobEvents } from './sse-transport'
import { useJobsStore } from '../../stores/jobs.store'

export class JobController {
  private stopped = false
  constructor(private readonly jobs: ReturnType<typeof useJobsStore>) {}
  async subscribe(jobId: string): Promise<void> {
    if (this.stopped) return
    const events = await readJobEvents(jobId, this.jobs.byId(jobId)?.lastEventId ?? 0)
    for (const event of events) this.jobs.applyEvent(jobId, event)
  }
  stopAll(): void { this.stopped = true }
}
