import { api } from '../../api/client'
import { ApiError } from '../../api/errors'
import { createIdempotencyKey } from './idempotency'
import type { PresentationMode } from '../../api/presentation.schemas'

export interface SubmissionInput {
  sessionId: string
  message: string
  fileId?: string
  mode: string
  presentationMode?: PresentationMode
}
interface Submission { key: string; digest: string; input: SubmissionInput }
const storageKey = (owner: string, sessionId: string) => `mathagent:submission:${encodeURIComponent(owner)}:${sessionId}`
export function readSubmission(owner: string, sessionId: string): Submission | null {
  const raw = localStorage.getItem(storageKey(owner, sessionId))
  return raw ? JSON.parse(raw) as Submission : null
}
export async function lookupSubmission(record: Submission) {
  try { return await api.submission(record.key) }
  catch (error) {
    if (error instanceof ApiError && error.status === 404 && error.code === 'job_not_found') return null
    throw error
  }
}
export async function submitOnce(owner: string, input: SubmissionInput) {
  if (!navigator.locks) throw new Error('浏览器不支持安全的多标签提交，请使用支持 Web Locks 的浏览器。')
  return navigator.locks.request(storageKey(owner, input.sessionId), async () => {
    const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(input)))
    const digest = Array.from(new Uint8Array(bytes), value => value.toString(16).padStart(2, '0')).join('')
    let record = readSubmission(owner, input.sessionId)
    if (record && record.digest !== digest) throw new Error('提交身份与输入冲突；请先核对原提交，或明确再次求解。')
    if (!record) {
      record = { key: createIdempotencyKey(), digest, input }
      localStorage.setItem(storageKey(owner, input.sessionId), JSON.stringify(record))
    } else {
      const found = await lookupSubmission(record)
      if (found) return found
    }
    return api.createJob(input.message, input.sessionId, record.key, input.fileId, input.mode, input.presentationMode)
  })
}
