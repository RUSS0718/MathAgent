import { z } from 'zod'
import { ApiError } from './errors'
import { checkAuthResponseSchema, logoutResponseSchema } from './auth.schemas'
import { activeJobsResponseSchema, jobActionResponseSchema } from './jobs.schemas'
import { changeSessionResponseSchema, deleteSessionResponseSchema, loadSessionResponseSchema, newChatResponseSchema, sessionsResponseSchema } from './sessions.schemas'
import { filesResponseSchema, uploadResponseSchema } from './files.schemas'
import { reportSchema } from './reports.schemas'
import { capabilitiesResponseSchema } from './capabilities.schemas'

let csrfToken = ''
export function setCsrfToken(value: string): void { csrfToken = value }

async function readBody(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text) return null
  try { return JSON.parse(text) as unknown } catch { return text }
}

async function requestJson<T>(input: string, init: RequestInit, schema: z.ZodType<T>): Promise<T> {
  let response: Response
  try {
    const headers = new Headers(init.headers)
    if (csrfToken && ['POST', 'PUT', 'PATCH', 'DELETE'].includes((init.method || 'GET').toUpperCase())) headers.set('X-CSRF-Token', csrfToken)
    response = await fetch(input, { credentials: 'same-origin', ...init, headers })
  } catch (cause) { throw new ApiError({ status: null, code: 'network_error', message: '无法连接服务器。', cause: cause as Error }) }
  const requestId = response.headers.get('X-Request-ID')
  const payload = await readBody(response)
  if (!response.ok) {
    const body = payload as { code?: unknown; error?: unknown } | null
    throw new ApiError({ status: response.status, code: typeof body?.code === 'string' ? body.code : 'request_failed', message: typeof body?.error === 'string' ? body.error : '请求失败。', requestId })
  }
  const parsed = schema.safeParse(payload)
  if (!parsed.success) throw new ApiError({ status: response.status, code: 'invalid_response', message: '服务器响应不符合协议。', requestId })
  return parsed.data
}

const json = (body: unknown): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const api = {
  checkAuth: () => requestJson('/api/check_auth', {}, checkAuthResponseSchema),
  logout: () => requestJson('/api/logout', json({}), logoutResponseSchema),
  listSessions: () => requestJson('/api/sessions', {}, sessionsResponseSchema),
  newChat: () => requestJson('/api/new_chat', json({}), newChatResponseSchema),
  loadSession: (id: string) => requestJson(`/api/load_session?session=${encodeURIComponent(id)}`, {}, loadSessionResponseSchema),
  changeSession: (id: string, title: string) => requestJson('/api/change_session', json({ session_id: id, title }), changeSessionResponseSchema),
  deleteSession: (id: string) => requestJson('/api/delete_session', json({ session_id: id }), deleteSessionResponseSchema),
  listFiles: () => requestJson('/api/files', {}, filesResponseSchema),
  uploadFile: (file: File) => { const body = new FormData(); body.append('file', file); return requestJson('/api/upload_file', { method: 'POST', body }, uploadResponseSchema) },
  deleteFile: (fileId: string) => requestJson('/api/delete_file', json({ file_id: fileId }), z.object({ success: z.boolean(), file_id: z.string() })),
  createJob: (message: string, sessionId: string, key: string, fileId?: string) => requestJson('/api/agent/jobs', { ...json({ message, session_id: sessionId, web_search_enabled: false, input_user_file_id: fileId }), headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key } }, jobActionResponseSchema),
  resumeJob: (jobId: string, answer: string, key: string) => requestJson(`/api/agent/jobs/${encodeURIComponent(jobId)}/resume`, { ...json({ answer }), headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key } }, jobActionResponseSchema),
  cancelJob: (jobId: string, key: string) => requestJson(`/api/agent/jobs/${encodeURIComponent(jobId)}/cancel`, { ...json({}), headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key } }, jobActionResponseSchema),
  activeJobs: (sessionId?: string) => requestJson(`/api/agent/jobs/active${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ''}`, {}, activeJobsResponseSchema),
  jobReport: (jobId: string) => requestJson(`/api/agent/jobs/${encodeURIComponent(jobId)}/report`, {}, reportSchema),
  capabilities: () => requestJson('/api/capabilities', {}, capabilitiesResponseSchema),
}
