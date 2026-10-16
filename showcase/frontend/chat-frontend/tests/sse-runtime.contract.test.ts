import assert from 'node:assert/strict'
import test from 'node:test'
import { decodeSseBlock, SseParser, SseProtocolError } from '../src/api/events.schemas.ts'
import { readJobEvents } from '../src/runtime/jobs/sse-transport.ts'

test('SSE parser joins UTF-8 data split across chunks and accepts heartbeat', () => {
  const parser = new SseParser()
  const bytes = new TextEncoder().encode(
    'id: 7\r\nevent: final_result\r\ndata: {"type":"final_result","data":{"summary":"答案：二"}}\r\n\r\n' +
    'event: heartbeat\r\ndata: {"type":"heartbeat","job_id":"job-1"}\r\n\r\n',
  )
  const split = bytes.indexOf(0xe4)
  const decoder = new TextDecoder()
  const blocks = parser.push(decoder.decode(bytes.slice(0, split), { stream: true }))
    .concat(parser.push(decoder.decode(bytes.slice(split), { stream: true })))
    .concat(parser.finish())
  const events = blocks.map(decodeSseBlock)
  assert.equal(events[0].id, 7)
  assert.equal((events[0].data.data as { summary: string }).summary, '答案：二')
  assert.equal(events[1].id, null)
})

test('protocol errors are stable and reject mismatched event/type', () => {
  assert.throws(
    () => decodeSseBlock({
      event: 'progress',
      id: '3',
      hasIdField: true,
      data: '{"type":"error","message":"坏包"}',
    }),
    (error: unknown) => error instanceof SseProtocolError && error.code === 'sse_protocol_error',
  )
})

test('transport sends query cursor first, Last-Event-ID on retry, and ignores duplicate IDs', async () => {
  const requests: Array<{ url: string; lastEventId: string | null }> = []
  const responses = [
    new Response(
      'id: 2\nevent: progress\ndata: {"type":"progress","step_id":"s1","node_name":"solve","title":"求解","summary":"一"}\n\n',
      { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
    ),
    new Response(
      'id: 2\nevent: progress\ndata: {"type":"progress","step_id":"s1","node_name":"solve","title":"求解","summary":"一"}\n\nid: 3\nevent: final_result\ndata: {"type":"final_result","data":{"summary":"完成"}}\n\n',
      { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
    ),
  ]
  const fetchImpl: typeof fetch = async (input, init) => {
    const headers = new Headers(init?.headers)
    requests.push({ url: String(input), lastEventId: headers.get('Last-Event-ID') })
    return responses.shift() as Response
  }
  const events = await readJobEvents('job/1', 1, { fetchImpl, retryDelayMs: 0, maxRetries: 2 })
  assert.deepEqual(events.map((event) => event.id), [2, 3])
  assert.equal(requests[0].url, '/api/agent/jobs/job%2F1/events?last_event_id=1')
  assert.equal(requests[0].lastEventId, null)
  assert.equal(requests[1].url, '/api/agent/jobs/job%2F1/events')
  assert.equal(requests[1].lastEventId, '2')
})
