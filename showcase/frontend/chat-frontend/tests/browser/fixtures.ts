import type { Page } from '@playwright/test'

/** Synthetic public report: this is presentation data, never capability evidence. */
export const report = {
  version: '1', evidence_id: 'evidence-demo', mode: 'fake', status: 'succeeded',
  report: {
    answer: '## 解题过程\n由 $x^2-5x+6=0$，因式分解得 $(x-2)(x-3)=0$。\n\n## 最终答案\n$x=2$ 或 $x=3$。',
    public_summary: '演示数据：候选根已代回检查，检查通过不等于一般数学证明。',
    stage: 'terminal',
    limitations: ['仅覆盖本例的多项式候选检查。'],
    checks: { status: 'pass', scope: 'candidate', checker: 'polynomial_check', findings: ['代回结果为 0'] },
    request_attempts: [{ attempt_id: 'attempt-demo', status: 'completed', requested_model: 'demo', duration_seconds: 1.25 }],
    tool_summaries: [{ name: 'polynomial_check', status: 'completed', result_summary: '候选根 2、3 代回为 0', limitations: ['不是完整证明'] }],
  },
}
const arm = { status: 'succeeded', job_id: 'run-demo', quality: { status: 'unknown' }, usage: { http_attempts: 1, unknown_attempts: 0 }, latency_seconds: 1.25, cost: null }
export const campaign = {
  campaign_id: 'campaign-demo', mode: 'fake', status: 'completed', common_hash: 'a'.repeat(64), config_hash: 'b'.repeat(64),
  summary: { total_pairs: 1, completed_pairs: 1, successful_pairs: 0 },
  pairs: [{ pair_id: 'pair-demo', problem_hash: 'c'.repeat(64), arms: { baseline: arm, candidate: { ...arm, status: 'failed', error: 'transport_timeout' } } }],
}

export async function mockWorkspace(page: Page, populated = false, eventStream?: string): Promise<void> {
  await page.route(/\/api\//, async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    if (!path.startsWith('/api/')) { await route.continue(); return }
    let body: unknown
    if (path === '/api/check_auth') body = { isLoggedIn: true, username: 'local', csrf_token: 'synthetic' }
    else if (path === '/api/sessions') body = [['session-demo', { preview: '多项式候选根验证', last_time: '2026-10-22 10:00' }]]
    else if (path === '/api/new_chat') body = { success: true, new_session_id: 'session-demo' }
    else if (path === '/api/load_session') body = { success: true, messages: populated ? [{ sender: 'user', text: '求解 x² − 5x + 6 = 0，并验证候选根。', analysis_job_id: 'run-demo' }] : [] }
    else if (path === '/api/capabilities') body = { profile: 'showcase', execution: { mode: 'fake', provider: 'demo', status: 'available' }, jobs: { enabled: true, status: 'available' }, sse: { enabled: true, status: 'available' }, verification_mode: ['auto'], files: { upload: { enabled: false } }, capabilities: { jobs: true, sse: true, verification_mode: ['auto'], file_upload: { enabled: false } } }
    else if (path === '/api/experiments/campaigns') body = { campaigns: [campaign], offset: 0, limit: 20 }
    else if (path.includes('/api/experiments/campaigns/')) body = campaign
    else if (path.endsWith('/report')) body = report
    else if (path.endsWith('/evidence')) body = { evidence_id: 'evidence-demo', mode: 'fake', run: {} }
    else if (path.endsWith('/events')) {
      await route.fulfill({ contentType: 'text/event-stream', body: eventStream ?? 'id: 1\nevent: node_end\ndata: {"type":"node_end","step_id":"solve","node_name":"solver","title":"求解","status":"completed","duration":1.25,"summary":"完成演示推导"}\n\nid: 2\nevent: final_result\ndata: {"type":"final_result","data":{},"status":"succeeded"}\n\n' })
      return
    } else if (path.startsWith('/api/agent/jobs/')) body = { success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'succeeded', last_event_id: 0 }
    else if (path === '/api/agent/jobs') body = { success: true, job_id: 'run-demo', status: 'succeeded' }
    else throw new Error(`Unmocked API: ${path}`)
    await route.fulfill({ json: body })
  })
}
