import { useEffect, useRef, useState } from 'react'
import { ImagePlus, X } from 'lucide-react'
import { modes, modeKeys, parseOutput, type OutputMode } from '@/lib/output-modes'
import { prepareQuestion, readWorkspace, submitPreparedQuestion, type ImageCapabilities } from '@/lib/image-workspace'
// Existing bookmarks used the Job rather than the session. Resolve through the ordinary API.
function SavedImageLink({ jobId }: { jobId: string }) {
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    const options = { signal: controller.signal }
    async function open() {
      await readWorkspace('/api/check_auth', options)
      const job = await readWorkspace<{ job_id: string; session_id: string }>('/api/agent/jobs/' + encodeURIComponent(jobId), options)
      if (job.job_id !== jobId || !job.session_id) throw new Error('找不到这道题的会话。')
      if (!controller.signal.aborted) location.replace('/dashboard/session/' + encodeURIComponent(job.session_id))
    }
    open().catch(e => { if (!controller.signal.aborted) setError(e.message) })
    return () => controller.abort()
  }, [jobId, attempt])
  return <section className="content conversation">{error ? <p role="alert">{error} <button onClick={() => {setError(''); setAttempt(n => n+1)}}>重新读取</button></p> : <p role="status">正在打开题图会话…</p>}</section>
}

export function ImageQuestion({ hash, initialInput, sampleUrl }: { hash: string; initialInput: string; sampleUrl: string }) {
  const parsed = parseOutput(initialInput)
  const [mode, setMode] = useState<OutputMode>(parsed.mode)
  const [text, setText] = useState(parsed.question)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState('')
  const [caps, setCaps] = useState<ImageCapabilities>()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [retry, setRetry] = useState(0)
  const lock = useRef(false)
  const input = useRef<HTMLInputElement>(null)
  const [, kind, id] = hash.split('/')
  const editing = !kind
  useEffect(() => {
    if (!editing) return
    const controller = new AbortController()
    readWorkspace<ImageCapabilities>('/api/capabilities', {signal:controller.signal}).then(value => {
      if (!value.files?.upload) throw new Error('服务未提供题图上传能力。')
      if (!controller.signal.aborted) { setCaps(value); setError('') }
    }).catch(e => { if (!controller.signal.aborted) setError(e.message) })
    return () => controller.abort()
  }, [editing, retry])
  useEffect(() => {
    if (!file) { setPreview(''); return }
    const url = URL.createObjectURL(file); setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])
  const limit = Math.min(caps?.files.upload.max_bytes ?? 131072, 131072)
  function choose(f: File | null) {
    setError(''); setFile(null)
    if (!f) return
    if (f.type !== 'image/png' || !f.size || f.size > limit) { setError(`请选择一张不超过 ${Math.floor(limit/1024)} KiB 的 PNG 题图。`); return }
    setFile(f)
  }
  async function useSample() {
    try {
      const response = await fetch(sampleUrl)
      if (!response.ok) throw new Error()
      choose(new File([await response.blob()], '示例方程.png', { type:'image/png' }))
    } catch { setError('示例题图读取失败，请重新选择题图。') }
  }
  async function send() {
    if (lock.current) return
    lock.current = true; setBusy(true); setError('')
    try {
      let key = id
      if (editing) {
        if (!caps?.files.upload.enabled || !file) return
        key = await prepareQuestion(file, text.trim(), mode, caps)
        if (window.location.hash !== '#image') return
        window.location.hash = 'image/pending/'+key
      }
      await submitPreparedQuestion(key, '#image/pending/'+key, !editing)
    } catch (e) { setError(e instanceof Error ? e.message : '题图提交失败。') }
    finally { lock.current = false; setBusy(false) }
  }
  if (kind === 'run' && id) return <SavedImageLink key={id} jobId={id}/>
  if (kind === 'pending') return <section className="content conversation image-view"><h1>题图提交</h1><p role="status">{busy ? '正在提交题图任务…' : '本次提交等待确认。'}</p>
    {error && <p className="error" role="alert">{error}</p>}<button className="primary-action" disabled={busy} onClick={send}>核对原提交</button></section>
  return <section className="content conversation image-view"><h1>题图求解</h1><p className="archive-source">上传一张 PNG，可另附解题要求。每张最多 {Math.floor(limit/1024)} KiB。</p>
    {!caps && !error && <p role="status">正在连接本机工作台…</p>}
    {caps && !caps.files.upload.enabled && <p role="status">当前工作台未开启题图上传。</p>}
    {caps?.files.upload.enabled && <form className="inline-panel image-form" onSubmit={e=>{e.preventDefault(); void send()}}>
      <input hidden ref={input} type="file" accept="image/png" aria-label="选择 PNG 题图" onChange={e=>{choose(e.target.files?.[0] ?? null); e.target.value=''}} disabled={busy}/>
      {file ? <div className="image-attachment">{preview && <img src={preview} alt="待提交的题图"/>}<span>{file.name}</span><button type="button" aria-label="移除题图" disabled={busy} onClick={()=>choose(null)}><X size={16}/></button></div>
      : <div className="file-options"><button type="button" className="file-picker" onClick={()=>input.current?.click()}><ImagePlus size={22}/>选择题图</button>
        <button type="button" className="sample-image" onClick={useSample}>使用示例题图</button></div>}
      <label>补充要求（可选）<textarea value={text} maxLength={32000} rows={2} disabled={busy} onChange={e=>setText(e.target.value)} placeholder="例如：请用手算，并代回检验。"/></label>
      <div className="image-toolbar"><select aria-label="题图输出模式" value={mode} disabled={busy} onChange={e=>setMode(e.target.value as OutputMode)}>{modeKeys.map(m=><option key={m} value={m}>/{m} · {modes[m]}</option>)}</select>
        <button type="submit" className="primary-action" disabled={!file || busy}>{busy ? '正在提交…' : '发送题图'}</button></div>
      {mode !== 'solve' && !(caps.presentation?.enabled && caps.presentation.modes.includes(mode)) && <small>此模式会作为题图的文字要求提交。服务提供原答复格式。</small>}
    </form>}
    {error && <p role="alert" className="error">{error} {!caps && <button onClick={()=>setRetry(n=>n+1)}>重新连接</button>}</p>}
  </section>
}
