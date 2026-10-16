export function acceptEventId(cursor: number, id: number | null): boolean {
  return id !== null && Number.isSafeInteger(id) && id > cursor
}

export interface EventCursors {
  transport: number
  rendered: number
}

export function acceptBusinessEvent(cursors: EventCursors, id: number | null): boolean {
  if (!acceptEventId(cursors.transport, id)) return false
  cursors.transport = id as number
  cursors.rendered = id as number
  return true
}

export function acceptUnknownEvent(cursors: EventCursors, id: number | null): boolean {
  if (!acceptEventId(cursors.transport, id)) return false
  cursors.transport = id as number
  return true
}
