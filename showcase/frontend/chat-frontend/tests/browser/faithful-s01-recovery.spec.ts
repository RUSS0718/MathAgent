import { expect, test } from '@playwright/test'
import { mockWorkspace, report } from './fixtures'

const firstEvent = 'id: 1\nevent: node_end\ndata: {"type":"node_end","step_id":"solve","node_name":"solver","title":"可重复节点","status":"completed","duration":1.25,"summary":"同一事件重放"}\n\n'
const resumedEvents = [
  firstEvent,
  'id: 2\nevent: node_end\ndata: {"type":"node_end","step_id":"review","node_name":"reviewer","title":"恢复后的节点","status":"completed","duration":0.5,"summary":"恢复事件"}\n\n',
  'id: 3\nevent: needs_review\ndata: {"type":"needs_review","status":"failed"}\n\n',
].join('')

test('refresh and SSE replay preserve unknown-call identity until explicit retry', async ({ page }) => {
  const pageErrors: string[] = []
  page.on('pageerror', error => pageErrors.push(error.message))
  await mockWorkspace(page)

  const jobReads: string[] = []
  const eventReads: { cursor: string | null; lastEventId: string | null }[] = []
  const resumePosts: Record<string, unknown>[] = []
  const createPosts: string[] = []
  page.on('request', request => {
    if (request.method() !== 'POST') return
    const url = new URL(request.url())
    if (url.pathname === '/api/agent/jobs') createPosts.push(url.pathname)
  })

  const unknownReport = {
    ...report,
    mode: 'star_limited',
    status: 'NEEDS_REVIEW',
    report: {
      ...report.report,
      budget: { http_attempts: 1, unknown_attempts: 1, reserved_tokens: 512, charged_tokens: 512, deadline_at: 1792770000 },
    },
    solver: {
      solver_mode: 'star_limited',
      evidence_kind: 'fault_injection',
      missing_capabilities: [],
      solver: {
        run_id: 'run-demo',
        state_revision: 5,
        phase: 'EXPLORE',
        status: 'interrupted',
        recovery: { status: 'needs_review', unknown_calls: [{ call_id: 'unknown-call', role: 'explore', status: 'unknown_outcome' }], retries: [] },
      },
    },
  }

  await page.route('**/api/agent/jobs/run-demo', async route => {
    if (route.request().method() !== 'GET') return route.fallback()
    jobReads.push(route.request().url())
    await route.fulfill({ json: {
      success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'failed', last_event_id: 0,
    } })
  })
  await page.route('**/api/agent/jobs/run-demo/report', route => route.fulfill({ json: unknownReport }))
  await page.route('**/api/agent/jobs/run-demo/events**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    eventReads.push({ cursor: url.searchParams.get('last_event_id'), lastEventId: request.headers()['last-event-id'] ?? null })
    const call = eventReads.length
    const body = call === 1 || call === 3
      ? firstEvent + firstEvent
      : call === 2 || call === 4
        ? firstEvent + resumedEvents
        : ''
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body })
  })
  await page.route('**/api/agent/jobs/run-demo/resume', async route => {
    if (route.request().method() !== 'POST') return route.fallback()
    resumePosts.push(route.request().postDataJSON() as Record<string, unknown>)
    await route.fulfill({ json: { success: true, job_id: 'run-demo', status: 'queued' } })
  })

  await page.goto('/dashboard-assets/run/run-demo')
  const retryAction = page.getByRole('button', { name: '明确选择：用新身份重试' })
  await expect(retryAction).toBeVisible()
  await expect(page.locator('.agent-timeline')).toContainText('3 个事件')
  await expect(page.locator('.timeline-steps .step-details li')).toHaveCount(3)
  expect(eventReads.slice(0, 2)).toEqual([
    { cursor: '0', lastEventId: null },
    { cursor: null, lastEventId: '1' },
  ])
  expect(createPosts).toEqual([])
  expect(resumePosts).toEqual([])

  await page.reload()
  await expect(retryAction).toBeVisible()
  await expect(page.locator('.agent-timeline')).toContainText('3 个事件')
  await expect(page.locator('.timeline-steps .step-details li')).toHaveCount(3)
  expect(eventReads.slice(2, 4)).toEqual([
    { cursor: '0', lastEventId: null },
    { cursor: null, lastEventId: '1' },
  ])
  expect(jobReads.length).toBeGreaterThanOrEqual(2)
  expect(createPosts).toEqual([])
  expect(resumePosts).toEqual([])

  await page.getByRole('button', { name: '重连事件（沿用游标）' }).click()
  await expect.poll(() => eventReads.length).toBe(7)
  expect(eventReads.slice(4)).toEqual([
    { cursor: '3', lastEventId: null },
    { cursor: null, lastEventId: '3' },
    { cursor: null, lastEventId: '3' },
  ])
  expect(createPosts).toEqual([])
  expect(resumePosts).toEqual([])

  await retryAction.click()
  await expect.poll(() => resumePosts.length).toBe(1)
  const retry = resumePosts[0]?.retry_call as { call_id: string; new_call_id: string }
  expect(retry.call_id).toBe('unknown-call')
  expect(retry.new_call_id).toMatch(/^[0-9a-f-]{36}$/)
  expect(retry.new_call_id).not.toBe(retry.call_id)
  expect(createPosts).toEqual([])
  expect(pageErrors).toEqual([])
})
