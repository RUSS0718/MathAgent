import assert from 'node:assert/strict'
import test from 'node:test'
import { readJobEvents } from '../src/runtime/jobs/sse-transport.ts'
test('196 ordinary whitelist SSE retains roles and terminal without technical fields', async () => {
 const events = await readJobEvents('ordinary', 0, { ordinary: true, maxRetries: 0, fetchImpl: async () => new Response('id: 1\nevent: progress\ndata: {"role":"planner","stage":"PLAN","summary":"正在制定计划"}\n\nid: 2\nevent: final_result\ndata: {"status":"succeeded"}\n\n') })
 assert.equal(events[0]?.data.role, 'planner')
 assert.equal(events[1]?.data.type, 'final_result')
})
