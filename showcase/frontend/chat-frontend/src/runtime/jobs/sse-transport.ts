import { decodeSseBlock, isTerminalEvent, SseParser, SseProtocolError, type DecodedSseEvent } from '../../api/events.schemas.ts'

export interface ReadJobEventsOptions {
  signal?: AbortSignal
  onEvent?: (event: DecodedSseEvent) => void | Promise<void>
  maxRetries?: number
  retryDelayMs?: number
  fetchImpl?: typeof fetch
}
export class SseTransportError extends Error {
  readonly code: string
  readonly status: number | null
  readonly retryable: boolean

  constructor(code: string, status: number | null = null, retryable = false) {
    super(code)
    this.name = 'SseTransportError'
    this.code = code
    this.status = status
    this.retryable = retryable
  }
}
function wait(delayMs: number, signal?: AbortSignal): Promise<void> {
  if (delayMs <= 0) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, delayMs)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(signal.reason ?? new DOMException('Aborted', 'AbortError'))
    }, { once: true })
  })
}

async function consumeResponse(
  response: Response,
  cursor: { value: number },
  events: DecodedSseEvent[],
  options: ReadJobEventsOptions,
): Promise<boolean> {
  if (!response.body) throw new SseProtocolError('SSE 响应没有可读取的 body')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  const parser = new SseParser()
  const accept = async (event: DecodedSseEvent): Promise<boolean> => {
    if (event.id !== null) {
      if (event.id <= cursor.value) return false
      cursor.value = event.id
    }
    events.push(event)
    await options.onEvent?.(event)
    // An interrupt is a successful observation boundary; resume opens a new stream.
    return isTerminalEvent(event) || event.event === 'interrupt'
  }
  try {
    while (true) {
      const chunk = await reader.read()
      if (chunk.done) break
      const text = decoder.decode(chunk.value, { stream: true })
      for (const block of parser.push(text)) {
        if (await accept(decodeSseBlock(block))) return true
      }
    }
    const tail = decoder.decode()
    for (const block of parser.push(tail)) {
      if (await accept(decodeSseBlock(block))) return true
    }
    for (const block of parser.finish()) {
      if (await accept(decodeSseBlock(block))) return true
    }
    return false
  } finally {
    reader.releaseLock()
  }
}

export async function readJobEvents(
  jobId: string,
  afterId = 0,
  options: ReadJobEventsOptions = {},
): Promise<DecodedSseEvent[]> {
  if (!Number.isSafeInteger(afterId) || afterId < 0) {
    throw new SseProtocolError('SSE 起始游标必须是非负安全整数')
  }
  const fetchImpl = options.fetchImpl ?? fetch
  const maxRetries = Math.max(0, options.maxRetries ?? 2)
  const retryDelayMs = Math.max(0, options.retryDelayMs ?? 50)
  const cursor = { value: afterId }
  const events: DecodedSseEvent[] = []
  let attempt = 0
  let first = true
  while (true) {
    options.signal?.throwIfAborted?.()
    const headers = new Headers()
    if (!first) headers.set('Last-Event-ID', String(cursor.value))
    const url = first
      ? '/api/agent/jobs/' + encodeURIComponent(jobId) + '/events?last_event_id=' + cursor.value
      : '/api/agent/jobs/' + encodeURIComponent(jobId) + '/events'
    let response: Response
    try {
      response = await fetchImpl(url, { credentials: 'same-origin', headers, signal: options.signal })
    } catch (cause) {
      if (options.signal?.aborted) throw cause
      if (attempt >= maxRetries) throw new SseTransportError('events_network_error', null, true)
      attempt += 1
      await wait(retryDelayMs * attempt, options.signal)
      first = false
      continue
    }
    if (!response.ok) {
      const retryable = response.status >= 500
      if (!retryable || attempt >= maxRetries) {
        throw new SseTransportError('events_' + response.status, response.status, retryable)
      }
      attempt += 1
      await wait(retryDelayMs * attempt, options.signal)
      first = false
      continue
    }
    try {
      const terminal = await consumeResponse(response, cursor, events, options)
      if (terminal) return events
    } catch (error) {
      if (error instanceof SseProtocolError) throw error
      if (options.signal?.aborted) throw error
      if (attempt >= maxRetries) throw new SseTransportError('events_stream_error', null, true)
    }
    if (attempt >= maxRetries) throw new SseTransportError('events_stream_ended', null, true)
    attempt += 1
    await wait(retryDelayMs * attempt, options.signal)
    first = false
  }
}

