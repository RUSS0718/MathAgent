import { z } from 'zod'

export const decodedSseEventSchema = z.object({
  id: z.number().int().positive().nullable(),
  event: z.string().min(1),
  data: z.record(z.string(), z.unknown()),
})
export type DecodedSseEvent = z.infer<typeof decodedSseEventSchema>

export interface RawSseBlock {
  event: string
  id: string | null
  hasIdField: boolean
  data: string
}

export class SseProtocolError extends Error {
  readonly code = 'sse_protocol_error'
  readonly rawBlock: RawSseBlock | null

  constructor(message: string, rawBlock: RawSseBlock | null = null) {
    super(message)
    this.name = 'SseProtocolError'
    this.rawBlock = rawBlock
  }
}

const knownPublicEventTypes = new Set([
  'queued',
  'running',
  'node_start',
  'progress',
  'decision',
  'decision_delta',
  'tool_call_start',
  'tool_call_result',
  'node_retry',
  'node_end',
  'text_delta',
  'final_result',
  'interrupt',
  'error',
  'canceled',
  'timeout',
  'needs_review',
  'heartbeat',
])

function parseEventId(raw: RawSseBlock): number | null {
  if (!raw.hasIdField || raw.id === null || raw.id === '') return null
  if (!/^\d+$/.test(raw.id)) throw new SseProtocolError('SSE 事件 ID 必须是非负整数文本', raw)
  const id = Number(raw.id)
  if (!Number.isSafeInteger(id) || id < 1) throw new SseProtocolError('SSE 事件 ID 超出有效范围', raw)
  return id
}

export function decodeSseBlock(raw: RawSseBlock): DecodedSseEvent {
  const event = raw.event.trim()
  if (!event) throw new SseProtocolError('SSE 事件名称不能为空', raw)
  if (!raw.data) throw new SseProtocolError('SSE 事件缺少 data 字段', raw)

  let parsed: unknown
  try {
    parsed = JSON.parse(raw.data)
  } catch {
    throw new SseProtocolError('SSE data 不是合法 JSON', raw)
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    throw new SseProtocolError('SSE data 必须是对象', raw)
  }
  const data = parsed as Record<string, unknown>
  if (typeof data.type !== 'string' || !data.type) {
    throw new SseProtocolError('SSE data 必须是带 type 的对象', raw)
  }
  if (data.type !== event) throw new SseProtocolError('SSE event 与 data.type 不一致', raw)

  const id = parseEventId(raw)
  if (event === 'heartbeat') {
    if (id !== null) throw new SseProtocolError('heartbeat 不应推进业务事件游标', raw)
  } else if (id === null) {
    throw new SseProtocolError('业务 SSE 事件必须带事件 ID', raw)
  }
  validatePublicEvent(event, data, raw)
  return { id, event, data }
}

function validatePublicEvent(event: string, data: Record<string, unknown>, raw: RawSseBlock): void {
  const requireString = (field: string) => {
    if (typeof data[field] !== 'string' || !data[field]) {
      throw new SseProtocolError('SSE 公共事件字段不符合协议', raw)
    }
  }
  const phase = () => {
    requireString('step_id')
    requireString('node_name')
    requireString('title')
  }
  if (event === 'heartbeat') {
    requireString('job_id')
  } else if (event === 'queued' || event === 'running') {
    requireString('job_id')
    requireString('status')
    phase()
    requireString('summary')
  } else if (event === 'progress' || event === 'decision') {
    phase()
    requireString('summary')
  } else if (event === 'decision_delta') {
    phase()
    requireString('stream_id')
    requireString('decision_kind')
    requireString('tool_name')
    if (!Number.isSafeInteger(data.sequence) || Number(data.sequence) < 1 || typeof data.delta !== 'string') {
      throw new SseProtocolError('SSE 公共事件字段不符合协议', raw)
    }
  } else if (event === 'tool_call_start') {
    phase()
    requireString('tool_name')
    if (!Array.isArray(data.argument_keys) || !data.argument_keys.every((value) => typeof value === 'string')) {
      throw new SseProtocolError('SSE 公共事件字段不符合协议', raw)
    }
  } else if (event === 'tool_call_result') {
    phase()
    requireString('tool_name')
    requireString('summary')
  } else if (event === 'node_retry') {
    phase()
    requireString('message')
  } else if (event === 'node_end') {
    phase()
    requireString('status')
    if (!['completed', 'failed'].includes(String(data.status)) || typeof data.duration !== 'number' || data.duration < 0) {
      throw new SseProtocolError('SSE 公共事件字段不符合协议', raw)
    }
  } else if (event === 'text_delta') {
    requireString('step_id')
    requireString('stream_id')
    if (!Number.isSafeInteger(data.sequence) || Number(data.sequence) < 1 || typeof data.delta !== 'string') {
      throw new SseProtocolError('SSE 公共事件字段不符合协议', raw)
    }
  } else if (event === 'final_result') {
    if (!('data' in data)) throw new SseProtocolError('SSE 公共事件字段不符合协议', raw)
  } else if (event === 'interrupt') {
    requireString('message')
    requireString('question_id')
  } else if (event === 'canceled') {
    requireString('job_id')
    requireString('status')
  } else if (event === 'error') {
    requireString('message')
  } else if (!knownPublicEventTypes.has(event)) {
    // Unknown events are intentionally accepted after the generic type check.
  }
}

function lineEndIndex(value: string): number {
  const lf = value.indexOf('\n')
  const cr = value.indexOf('\r')
  if (lf === -1) return cr
  if (cr === -1) return lf
  return Math.min(lf, cr)
}

export class SseParser {
  private buffer = ''
  private event = 'message'
  private id: string | null = null
  private hasIdField = false
  private dataLines: string[] = []

  push(chunk: string): RawSseBlock[] {
    this.buffer += chunk
    const blocks: RawSseBlock[] = []
    while (true) {
      const end = lineEndIndex(this.buffer)
      if (end < 0) break
      const isCr = this.buffer[end] === '\r'
      if (isCr && end === this.buffer.length - 1) break
      const separatorLength = isCr && this.buffer[end + 1] === '\n' ? 2 : 1
      const line = this.buffer.slice(0, end)
      this.buffer = this.buffer.slice(end + separatorLength)
      const block = this.consumeLine(line)
      if (block) blocks.push(block)
    }
    return blocks
  }

  finish(): RawSseBlock[] {
    const blocks: RawSseBlock[] = []
    if (this.buffer) {
      const block = this.consumeLine(this.buffer)
      if (block) blocks.push(block)
      this.buffer = ''
    }
    const finalBlock = this.dispatch()
    if (finalBlock) blocks.push(finalBlock)
    return blocks
  }

  private consumeLine(line: string): RawSseBlock | null {
    if (line === '') return this.dispatch()
    if (line.startsWith(':')) return null
    const separator = line.indexOf(':')
    const field = separator < 0 ? line : line.slice(0, separator)
    let value = separator < 0 ? '' : line.slice(separator + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') this.event = value
    else if (field === 'id') {
      this.id = value
      this.hasIdField = true
    } else if (field === 'data') this.dataLines.push(value)
    return null
  }

  private dispatch(): RawSseBlock | null {
    if (this.dataLines.length === 0) {
      this.event = 'message'
      this.id = null
      this.hasIdField = false
      return null
    }
    const block: RawSseBlock = {
      event: this.event,
      id: this.id,
      hasIdField: this.hasIdField,
      data: this.dataLines.join('\n'),
    }
    this.event = 'message'
    this.id = null
    this.hasIdField = false
    this.dataLines = []
    return block
  }
}

export function isTerminalEvent(event: DecodedSseEvent): boolean {
  return event.event === 'final_result' || event.event === 'error' || event.event === 'canceled' || event.event === 'timeout' || event.event === 'needs_review'
}
