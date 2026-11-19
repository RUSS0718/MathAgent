import { lazy, Suspense, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { History, Pencil, Trash2 } from 'lucide-react'
import { Dashboard } from './components/Dashboard'
import { NavigationRow, Section } from './components/sidebar/NavigationPrimitives'
import { readWorkspace, writeWorkspace } from './lib/image-workspace'
import { themeKey } from './lib/theme'
import 'katex/dist/katex.min.css'
import './app/globals.css'
import './features/ui-layout/modern/modern.css'
import './app/workspace.css'

const SessionBody = lazy(() => import('./workbench-session'))
function Session({ id }) {
  return <Suspense fallback={<p role="status" className="content conversation">正在读取会话…</p>}><SessionBody id={id}/></Suspense>
}
function Library({ id, query }) {
  const [sessions, setSessions] = useState([])
  const [reviewer, setReviewer] = useState(false)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    const options = { signal: controller.signal }
    async function load() {
      const auth = await readWorkspace('/api/check_auth', options)
      const list = await readWorkspace('/api/sessions', options)
      if (!controller.signal.aborted) {
        setReviewer(auth.permissions?.includes('reviewer.access') ?? false); setSessions(list); setError('')
      }
    }
    load().catch(e => { if (!controller.signal.aborted) setError(e.message) })
    return () => controller.abort()
  }, [revision])
  async function edit(sessionId, previous, remove) {
    const title = remove ? undefined : window.prompt('会话名称', previous)?.trim()
    if (remove ? !window.confirm('删除此会话？此操作无法撤销。') : !title) return
    try {
      await writeWorkspace(remove ? '/api/delete_session' : '/api/change_session', { session_id: sessionId, title })
      if (remove && id === sessionId) location.assign('/dashboard')
      else setRevision(n => n + 1)
    } catch (failure) { setError(failure.message) }
  }
  return <>{(sessions.length > 0 || error) && <Section title="我的会话">
    {sessions.filter(([, info]) => info.preview.toLowerCase().includes(query.toLowerCase())).map(([sessionId, info]) => <div className="saved-session-row" key={sessionId}>
      <NavigationRow icon={History} label={info.preview} active={id === sessionId} onClick={() => location.assign('/dashboard/session/' + encodeURIComponent(sessionId))}/>
      <button title={'重命名会话：'+info.preview} onClick={() => edit(sessionId, info.preview, false)}><Pencil size={13}/></button>
      <button title={'删除会话：'+info.preview} onClick={() => edit(sessionId, info.preview, true)}><Trash2 size={13}/></button>
    </div>)}
    {error && <small role="alert">{error} <button onClick={() => setRevision(n => n + 1)}>重试</button></small>}
  </Section>}{reviewer && <Section title="技术审阅"><a href="/dashboard/settings">设置</a> · <a href="/dashboard/campaigns">配对实验</a></Section>}</>
}
try { if (localStorage.getItem(themeKey) === 'dark') document.documentElement.classList.replace('theme-snow', 'dark') } catch {}
createRoot(document.getElementById('workbench')).render(<Dashboard service={{ Session, Library, reviewerLink:<a href="/dashboard/reviewer">技术审阅授权</a> }}/>)
