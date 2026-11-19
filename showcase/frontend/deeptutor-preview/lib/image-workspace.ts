import { modeKeys, type OutputMode } from './output-modes'

export interface ImageCapabilities {
  files: { upload: { enabled: boolean; max_bytes?: number } }
  presentation?: { enabled: boolean; modes: string[] }
}
export async function readWorkspace<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { cache: 'no-store', ...init })
  const payload = await response.json().catch(() => null)
  if (!response.ok || !payload) throw new Error(payload?.message ?? payload?.error ?? '暂时无法连接本机工作台，请重试。')
  return payload
}
function post(body: unknown, token: string, key?: string): RequestInit {
  const headers = new Headers({ 'X-CSRF-Token': token })
  if (key) headers.set('Idempotency-Key', key)
  if (body instanceof FormData) return { method:'POST', headers, body }
  headers.set('Content-Type','application/json')
  return { method:'POST', headers, body: JSON.stringify(body) }
}
async function csrf() {
  const auth = await readWorkspace<{ csrf_token: string }>('/api/check_auth')
  if (!auth.csrf_token) throw new Error('无法建立本机会话，请重新连接。')
  return auth.csrf_token
}
export async function writeWorkspace(path: string, body: unknown) {
  return readWorkspace(path, post(body, await csrf()))
}
export async function prepareQuestion(file: File | null, text: string, mode: OutputMode, capabilities: ImageCapabilities) {
  const token = await csrf()
  let fileId: string | undefined
  if (file) {
    const form = new FormData(); form.append('file', file)
    const upload = await readWorkspace<{ file: { file_id: string } }>('/api/upload_file', post(form, token))
    fileId = upload.file?.file_id
    if (!fileId) throw new Error('上传未返回题图编号。')
  }
  const session = await readWorkspace<{ new_session_id: string }>('/api/new_chat',post({},token))
  if (!session.new_session_id) throw new Error('未能建立会话。')
  const formatting = { solve:'', teach:'请用教学方式引导解题，并提供逐步提示。', report:'请用求解报告格式给出题目、结论、推导和检查范围。', explore:'请探索可行的解题路线，比较思路并说明如何检验。' }
  const native = capabilities.presentation?.enabled && capabilities.presentation.modes.includes(mode)
  const message = native || mode === 'solve' ? text : [text, formatting[mode]].filter(Boolean).join('\n')
  const key = crypto.randomUUID()
  const body = { session_id:session.new_session_id, message, input_user_file_id:fileId, ...(native ? { presentation_mode:mode } : {}) }
  sessionStorage.setItem('mathagent:image:'+key, JSON.stringify({ mode, body }))
  return key
}
export async function submitPreparedQuestion(key: string, fragment: string, recover: boolean) {
  const raw = sessionStorage.getItem('mathagent:image:'+key)
  if (!raw) throw new Error('本标签页找不到这次提交。请返回新建题目。')
  const { mode, body } = JSON.parse(raw) as { mode:OutputMode; body:{ session_id:string } }
  const token = await csrf()
  let result: { job_id: string; session_id?: string } | undefined
  if (recover) {
    const response = await fetch('/api/agent/submissions/'+encodeURIComponent(key), { cache: 'no-store' })
    const saved = await response.json()
    if (response.ok && saved.session_id === body.session_id && saved.job_id) result = saved
    else if (response.status !== 404 || saved.code !== 'job_not_found') throw new Error('暂时无法确认原提交，请重试。')
  }
  result ??= await readWorkspace('/api/agent/jobs', post(body, token, key))
  if (!result?.job_id || (result.session_id && result.session_id !== body.session_id)) throw new Error('服务尚未确认原任务。')
  localStorage.setItem('mathagent:image-mode:'+result.job_id, mode)
  if (location.hash === fragment) {
    if (!recover) sessionStorage.setItem('mathagent:just-submitted:'+body.session_id, result.job_id)
    location.replace('/dashboard/session/' + encodeURIComponent(body.session_id))
    sessionStorage.removeItem('mathagent:image:' + key)
  }
}

export function requestedImageMode(jobId: string) {
  const key = 'mathagent:image-mode:' + jobId
  const requested = localStorage.getItem(key) ?? sessionStorage.getItem(key)
  return modeKeys.find(mode => mode === requested)
}
