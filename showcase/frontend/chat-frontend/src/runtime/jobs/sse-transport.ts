import { decodedSseEventSchema, type DecodedSseEvent } from '../../api/events.schemas'

export async function readJobEvents(jobId: string, afterId = 0): Promise<DecodedSseEvent[]> {
  const response = await fetch(`/api/agent/jobs/${encodeURIComponent(jobId)}/events?last_event_id=${afterId}`, { credentials: 'same-origin' })
  if (!response.ok) throw new Error(`events_${response.status}`)
  const text = await response.text()
  const events: DecodedSseEvent[] = []
  for (const block of text.split(/\n\n+/)) {
    const id = block.match(/^id:\s*(\d+)/m)?.[1]
    const event = block.match(/^event:\s*(\S+)/m)?.[1]
    const data = block.match(/^data:\s*(.+)$/m)?.[1]
    if (!id || !event || !data) continue
    const parsed = decodedSseEventSchema.safeParse({ id: Number(id), event, data: JSON.parse(data) })
    if (parsed.success) events.push(parsed.data)
  }
  return events
}
