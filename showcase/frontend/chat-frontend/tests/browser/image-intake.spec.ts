import { expect, test } from '@playwright/test'
import { mockWorkspace } from './fixtures'

test('submits an image without typing and restores the saved image intake on refresh', async ({ page }, info) => {
  await mockWorkspace(page)
  let solvePosts = 0
  let jobReadsAfterIntake = 0
  let ready = false
  let finishStream!: () => void
  const releaseStream = new Promise<void>(resolve => { finishStream = resolve })
  const file = { file_id: 'file-demo', reference: 'file-demo', mime: 'image/png', size: 70, sha256: 'fixture', status: 'ready' }
  await page.route('**/api/capabilities', route => route.fulfill({ json: {
    profile: 'showcase', jobs: { enabled: true, status: 'available' }, sse: { enabled: true, status: 'available' },
    files: { upload: { enabled: true } },
  } }))
  await page.route('**/api/files', route => route.fulfill({ json: [] }))
  await page.route('**/api/upload_file', route => route.fulfill({ json: { file } }))
  await page.route('**/api/load_session?*', route => route.fulfill({ json: { success: true,
    messages: solvePosts ? [{ sender: 'user', text: '', analysis_job_id: 'run-demo' }] : [] } }))
  const pendingJob = { success: true, job_id: 'run-demo', session_id: 'session-demo', status: 'running',
    input_user_file_id: file.file_id, result: { input_intake: { modality: 'image', status: 'pending' } } }
  const job = { ...pendingJob, status: 'succeeded', result: { input_intake: { modality: 'image', status: 'ready', problem_type: 'equation' } } }
  await page.route('**/api/agent/submissions/*', route => route.fulfill({ json: ready ? job : pendingJob }))
  await page.route('**/api/agent/jobs/run-demo', route => {
    if (ready) jobReadsAfterIntake += 1
    return route.fulfill({ json: ready ? job : pendingJob })
  })
  await page.route('**/api/agent/jobs/run-demo/events*', async route => {
    await releaseStream
    return route.fulfill({ contentType: 'text/event-stream', body:
      'id: 1\nevent: progress\ndata: {"type":"progress","stage":"image_intake_ready","status":"running"}\n\n' +
      'id: 2\nevent: final_result\ndata: {"type":"final_result","status":"succeeded"}\n\n',
    })
  })
  await page.route('**/api/agent/jobs/run-demo/answer', route => route.fulfill({ json: {
    job_id: 'run-demo', status: 'succeeded', mode: 'solve', presentation_status: 'ready', answer: 'x=1',
  } }))
  await page.route('**/api/agent/jobs', route => {
    solvePosts += 1
    expect(route.request().postDataJSON()).toMatchObject({ message: '', input_user_file_id: file.file_id })
    return route.fulfill({ status: 202, json: pendingJob })
  })
  await page.goto('/dashboard-assets/session/session-demo')
  const send = page.getByRole('button', { name: '发送', exact: true })
  await expect(send).toBeDisabled()
  await page.locator('input[type=file]').setInputFiles({ name: 'question.png', mimeType: 'image/png', buffer: Buffer.from('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cf00000004000101e2dd0000000049454e44ae426082', 'hex') })
  await expect(send).toBeEnabled()
  await send.click()
  await expect(page.getByText('正在读取题图…', { exact: true })).toBeVisible()
  ready = true
  finishStream()
  await expect(page.getByText('已读取题图。', { exact: true })).toBeVisible()
  await expect(page.getByText('方程题', { exact: true })).toBeVisible()
  expect(jobReadsAfterIntake).toBeGreaterThan(0)
  await page.reload()
  await expect(page.getByText('方程题', { exact: true })).toBeVisible()
  expect(solvePosts).toBe(1)
  await page.screenshot({ path: info.outputPath('image-intake.png') })
})
