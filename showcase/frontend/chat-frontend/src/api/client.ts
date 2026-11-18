import { campaignSchema, campaignsSchema } from './campaigns.schemas'
import { z } from 'zod'
import { ApiError } from './errors'
import { checkAuthResponseSchema, logoutResponseSchema } from './auth.schemas'
import { activeJobsResponseSchema, jobActionResponseSchema, jobResponseSchema } from './jobs.schemas'
import { changeSessionResponseSchema, deleteSessionResponseSchema, loadSessionResponseSchema, newChatResponseSchema, sessionsResponseSchema } from './sessions.schemas'
import { filesResponseSchema, uploadResponseSchema } from './files.schemas'
import { reportSchema } from './reports.schemas'
import { capabilitiesResponseSchema } from './capabilities.schemas'
import { presentationResponseSchema, type PresentationMode } from './presentation.schemas'
import { populationMemoryControlResponseSchema, populationMemoryResponseSchema, populationMemoryUpdateResponseSchema, runMemoryResponseSchema } from './memory.schemas'
import { goalCacheResponseSchema } from './goal-cache.schemas'
import { interventionMutationSchema, interventionsResponseSchema, type CreateInterventionActionInput, type CreateInterventionHypothesisInput, type ReserveInterventionPairInput } from './interventions.schemas'
import { systemRunResponseSchema, systemRunsResponseSchema, type SystemRunResponse } from './system.schemas'
import type { SystemDeepLinkState } from '../runtime/navigation/system-deeplink'

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
  campaigns: (offset = 0) => requestJson('/api/experiments/campaigns?offset=' + offset + '&limit=20', {}, campaignsSchema),
  campaign: (id: string) => requestJson('/api/experiments/campaigns/' + encodeURIComponent(id), {}, campaignSchema),
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
  createJob: (message: string, sessionId: string, key: string, fileId?: string, solverMode = 'legacy', presentationMode?: PresentationMode) => requestJson('/api/agent/jobs', { ...json({ message, session_id: sessionId, web_search_enabled: false, input_user_file_id: fileId, solver_mode: solverMode, ...(presentationMode ? { presentation_mode: presentationMode } : {}) }), headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key } }, jobActionResponseSchema),
  resumeJob: (jobId: string, answer: string, key: string) => requestJson(`/api/agent/jobs/${encodeURIComponent(jobId)}/resume`, { ...json({ answer }), headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key } }, jobActionResponseSchema),
  retryUnknownCall: (jobId: string, callId: string, newCallId: string, key: string) => requestJson(`/api/agent/jobs/${encodeURIComponent(jobId)}/resume`, { ...json({ retry_call: { call_id: callId, new_call_id: newCallId } }), headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key } }, jobActionResponseSchema),
  cancelJob: (jobId: string, key: string) => requestJson(`/api/agent/jobs/${encodeURIComponent(jobId)}/cancel`, { ...json({}), headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key } }, jobActionResponseSchema),
  activeJobs: (sessionId?: string) => requestJson(`/api/agent/jobs/active${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ''}`, {}, activeJobsResponseSchema),
  getJob: (jobId: string) => requestJson(`/api/agent/jobs/${encodeURIComponent(jobId)}`, {}, jobResponseSchema),
  jobReport: (jobId: string) => requestJson(`/api/agent/jobs/${encodeURIComponent(jobId)}/report`, {}, reportSchema),
  presentation: (jobId: string, mode: PresentationMode) => requestJson(`/api/agent/jobs/${encodeURIComponent(jobId)}/${mode}`, json({}), presentationResponseSchema),
  evidence: (jobId: string) => requestJson('/api/runs/' + encodeURIComponent(jobId) + '/evidence', {}, z.object({ evidence_id: z.string(), mode: z.string(), run: z.record(z.string(), z.unknown()) }).passthrough()),
  candidateReplay: (jobId: string) => requestJson(`/api/agent/jobs/${encodeURIComponent(jobId)}/candidate-replay`, {}, z.object({ evidence_kind: z.literal('replay'), run_id: z.string(), state_revision: z.number(), audit: z.record(z.string(), z.unknown()), decision: z.unknown() })),
  runMemory: (jobId: string) => requestJson(`/api/agent/jobs/${encodeURIComponent(jobId)}/memory`, {}, runMemoryResponseSchema),
  populationMemory: (sessionId: string) => requestJson(`/api/sessions/${encodeURIComponent(sessionId)}/population-memory`, {}, populationMemoryResponseSchema),
  populationMemoryControl: async (sessionId: string) => {
    if (!sessionId) throw new ApiError({ status: 404, code: 'session_unavailable', message: '会话记忆不可用。' })
    const data = await requestJson(`/api/sessions/${encodeURIComponent(sessionId)}/memory/population/${encodeURIComponent(sessionId)}`, {}, populationMemoryControlResponseSchema)
    return { ...data, sessionId }
  },
  setPopulationMemoryInjection: async (sessionId: string, enabled: boolean) => {
    if (!sessionId) throw new ApiError({ status: 404, code: 'session_unavailable', message: '会话记忆不可用。' })
    return requestJson(
      `/api/sessions/${encodeURIComponent(sessionId)}/memory/population/${encodeURIComponent(sessionId)}/injection`,
      { ...json({ enabled }), method: 'PUT' },
      populationMemoryUpdateResponseSchema,
    )
  },
  goalCache: (sessionId: string) => requestJson(`/api/sessions/${encodeURIComponent(sessionId)}/goal-cache`, {}, goalCacheResponseSchema),
  setGoalCacheEnabled: (sessionId: string, enabled: boolean) => requestJson(`/api/sessions/${encodeURIComponent(sessionId)}/goal-cache`, { ...json({ enabled }), method: 'PUT' }, z.unknown()),
  clearGoalCache: (sessionId: string) => requestJson(`/api/sessions/${encodeURIComponent(sessionId)}/goal-cache`, { method: 'DELETE' }, z.unknown()),
  interventions: (jobId: string) => requestJson(`/api/agent/jobs/${encodeURIComponent(jobId)}/interventions`, {}, interventionsResponseSchema),
  requestInterventionPause: (jobId: string) => requestJson(`/api/agent/jobs/${encodeURIComponent(jobId)}/interventions/pause`, json({}), interventionMutationSchema),
  createInterventionHypothesis: (jobId: string, body: CreateInterventionHypothesisInput) => requestJson(`/api/agent/jobs/${encodeURIComponent(jobId)}/interventions/hypotheses`, json(body), interventionMutationSchema),
  createInterventionAction: (jobId: string, body: CreateInterventionActionInput) => requestJson(`/api/agent/jobs/${encodeURIComponent(jobId)}/interventions/actions`, json(body), interventionMutationSchema),
  reserveInterventionPair: (jobId: string, body: ReserveInterventionPairInput) => requestJson(`/api/agent/jobs/${encodeURIComponent(jobId)}/interventions/pairs`, json(body), interventionMutationSchema),
  executeInterventionPair: (jobId: string, pairId: string) => requestJson(`/api/agent/jobs/${encodeURIComponent(jobId)}/interventions/pairs/${encodeURIComponent(pairId)}/execute`, json({}), interventionMutationSchema),
  resumeInterventionParent: (jobId: string, key: string) => requestJson(`/api/agent/jobs/${encodeURIComponent(jobId)}/interventions/resume`, { ...json({}), headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key } }, jobActionResponseSchema),
  capabilities: () => requestJson('/api/capabilities', {}, capabilitiesResponseSchema),
  faithfulRuns: (limit = 50, offset = 0) => requestJson(`/api/faithful/runs?limit=${limit}&offset=${offset}`, {}, systemRunsResponseSchema),
  faithfulRun: (state: SystemDeepLinkState) => {
    const query = new URLSearchParams({ scheme: 'f7-deeplink-v1' })
    if (state.mode) query.set('mode', state.mode)
    if (state.outputId) query.set('output', state.outputId)
    if (state.artifactId) query.set('artifact', state.artifactId)
    if (state.graphVersion !== undefined) query.set('graph', String(state.graphVersion))
    if (state.nodeId) query.set('node', state.nodeId)
    if (state.paragraphId) query.set('paragraph', state.paragraphId)
    return requestJson(`/api/faithful/runs/${encodeURIComponent(state.runId)}?${query}`, {}, systemRunResponseSchema)
  },
}
