'use client'
import { useEffect, useRef, useState, useSyncExternalStore, type ComponentType, type ReactNode } from 'react'
import { ArrowUpRight, Compass, FunctionSquare, GitBranch, History, Menu, MessageSquare, Plus, Search, Sigma, SquarePen } from 'lucide-react'
import { NavigationRow, Section } from '@/components/sidebar/NavigationPrimitives'
import { Composer } from '@/components/chat/home/Composer'
import { AssistantResponse } from '@/components/common/AssistantResponse'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Progress } from '@/components/Progress'
import { ArchiveReplay } from '@/components/ArchiveReplay'
import { ImageQuestion } from '@/components/ImageQuestion'
import { prepareQuestion, submitPreparedQuestion, readWorkspace, type ImageCapabilities } from '@/lib/image-workspace'
import { TriangleClarification } from '@/components/TriangleClarification'
import { Button } from '@/shared/ui/Button'
import { Dialog } from '@/shared/ui/Dialog'
import { examples, stepsFor, type Example } from '@/lib/examples'
import { modes, parseOutput, withMode, type OutputMode } from '@/lib/output-modes'
import { triangleQuestion, triangleResult, triangleTitle } from '@/lib/triangle'

type Submission = { id: string; example: Example | null; mode: OutputMode; completed: number; parentId?: string }
const starters = [...examples, { title: triangleTitle, subject: '条件澄清演示', question: triangleQuestion }]
const subscribeHash = (listener: () => void) => {
  window.addEventListener('hashchange', listener)
  window.addEventListener('popstate', listener)
  return () => { window.removeEventListener('hashchange', listener); window.removeEventListener('popstate', listener) }
}

export interface WorkspaceViews {
  Session: ComponentType<{ id: string }>
  Library: ComponentType<{ id: string | null; query: string }>
  reviewerLink: ReactNode
}

export function Dashboard({ service }: { service?: WorkspaceViews }) {
  const [input, setInput] = useState('')
  const [chosenExample, setChosenExample] = useState('')
  const [error, setError] = useState('')
  const [activeId, setActiveId] = useState<string | null>(null)
  const [history, setHistory] = useState<Submission[]>([])
  const [drawer, setDrawer] = useState(false)
  const [search, setSearch] = useState<string | null>(null)
  const [paused, setPaused] = useState(false)
  const route = useSyncExternalStore(subscribeHash, () => location.pathname + location.hash, () => '')
  const [path, fragment = ''] = route.split('#')
  const hash = '#' + fragment
  const session = service && /^\/dashboard\/session\/([A-Za-z0-9._-]{1,64})$/.exec(path)?.[1]
  const pending = !!service && hash.startsWith('#submit/')
  const sending = useRef(false)
  const [busy, setBusy] = useState(false)
  const archive = /^#d2(?:\/[1-3])?$/.test(hash)
  const image = hash === '#image' || hash.startsWith('#image/')
  const active = history.find(item => item.id === activeId)
  const completed = active?.completed ?? 0
  const example = active?.example
  const total = example ? stepsFor(example).length : 0
  const finished = !!example && completed === total
  const parent = history.find(item => item.id === active?.parentId)
  const child = active && history.find(item => item.parentId === active.id)
  const title = session ? '会话记录' : pending ? '提交题目' : archive ? 'D2 公开成果摘录' : image ? service ? '题图求解' : '题图示例' : active ? example?.title ?? triangleTitle : '新建题目'
  useEffect(() => {
    if (!example || paused || finished || archive || image || session || pending) return
    const timer = window.setTimeout(() => {
      setHistory(items => items.map(item => item.id === activeId ? { ...item, completed:item.completed+1 } : item))
    }, example.script ? 3200 : 1250)
    return () => window.clearTimeout(timer)
  }, [activeId, completed, paused, finished, example, archive, image, session, pending])
  function updateActive(values: Partial<Pick<Submission, 'completed' | 'example'>>) {
    setHistory(items => items.map(item => item.id === activeId ? { ...item, ...values } : item))
  }
  function navigate(fragment: string) {
    if (session) {
      window.history.pushState(null, '', '/dashboard' + (fragment ? '#' + fragment : ''))
      window.dispatchEvent(new PopStateEvent('popstate'))
    } else window.location.hash = fragment
    setDrawer(false)
  }
  function reopen(item: Submission) { navigate(''); setActiveId(item.id); setPaused(false) }
  function createTask(example: Example | null, mode: OutputMode, parentId?: string) {
    const task = { id:crypto.randomUUID(), example, mode, parentId, completed:0 }
    setHistory(items => [task,...items]); reopen(task)
  }
  function home(text = '') {
    navigate(''); setActiveId(null); setPaused(false); setChosenExample(text)
    setInput(text ? withMode(!active ? parseOutput(input).mode : 'solve', text) : ''); setError('')
  }
  async function sendText(question: string, mode: OutputMode, pendingKey?: string) {
    if (sending.current) return
    sending.current = true; setBusy(true); setError('')
    const from = location.href
    try {
      let key = pendingKey
      if (!key) {
        const caps = await readWorkspace<ImageCapabilities>('/api/capabilities')
        key = await prepareQuestion(null, question, mode, caps)
        if (from !== location.href) return
        navigate('submit/' + key)
      }
      await submitPreparedQuestion(key, '#submit/' + key, Boolean(pendingKey))
    } catch (failure) { setError(failure instanceof Error ? failure.message : '题目提交失败。') }
    finally { sending.current = false; setBusy(false) }
  }
  function submit() {
    const { mode, question } = parseOutput(input)
    if (!question) { setError('请选择示例题目，或在命令后输入示例原题。'); return }
    if (service && question !== chosenExample) { void sendText(question, mode); return }
    const record = examples.find(e => e.question === question)
    if (!record && question !== triangleQuestion) { setError('请选择下方示例进行模拟。'); return }
    createTask(record ?? null, mode); setError('')
  }
  function openVariant() {
    if (!active || !example?.variant) return
    if (child) { reopen(child); return }
    createTask(example.variant, active.mode, active.id)
  }
  const side = <nav aria-label="工作台导航" className="dt-product-sidebar side-content">
    <div className="brand"><span className="brand-mark"><Sigma size={18}/></span>MathAgent</div>
    <NavigationRow label="新建题目" icon={SquarePen} active={!active && !archive && !image && !session && !pending} onClick={() => home()} />
    <NavigationRow label="搜索题目" icon={Search} active={search !== null} onClick={() => setSearch(search === null ? '' : null)} />
    {search !== null && <input autoFocus aria-label="搜索题目" placeholder="搜索示例和最近题目" className="search" value={search} onChange={e => setSearch(e.target.value)} />}
    <Section title="示例题库">{starters.filter(e => e.title.includes((search ?? '').trim())).map(e => <NavigationRow key={e.title} label={e.title} icon={MessageSquare} onClick={() => home(e.question)} />)}
      {search && !starters.some(e => e.title.includes(search.trim())) && <small>没有匹配的题目</small>}</Section>
    <Section title="公开摘录"><NavigationRow label="D2 公开成果摘录" icon={History} active={archive} onClick={() => navigate('d2')} /></Section>
    {service && <service.Library id={session || null} query={(search ?? '').trim()}/>}
    {history.length > 0 && <Section title="最近题目">{history.filter(item => (item.example?.title ?? triangleTitle).includes((search ?? '').trim())).map(item => <NavigationRow key={item.id} label={(item.example?.title ?? triangleTitle)+' · '+modes[item.mode]} icon={History} active={!archive && !image && !session && !pending && active?.id === item.id} onClick={() => reopen(item)} />)}</Section>}
    <div className="side-foot"><span className="status-light"/>本地工作区{service?.reviewerLink}</div>
  </nav>
  return <div className="workspace"><aside className="desktop-side">{side}</aside>
    <main><header className="pagebar"><button className="mobile-menu dt-nav-icon" onClick={() => setDrawer(true)} title="打开导航" aria-label="打开导航"><Menu size={19}/></button>
      <Compass size={16}/>数学工作台<span className="separator">/</span><span className="page-title">{title}</span><small className="source-label">{session ? '已保存的会话' : archive ? '公开摘录' : image && service ? '题图工作台' : service && !active && (!chosenExample || parseOutput(input).question !== chosenExample) ? '本机工作台' : '模拟运行'}</small><ThemeToggle /></header>
    {session && service ? <service.Session key={session} id={session}/> : pending ? <section className="content conversation"><h1>提交题目</h1>
      <p role="status">{busy ? '正在提交…' : '本次提交等待确认。'}</p>{error && <p className="error" role="alert">{error}</p>}
      <button className="primary-action" disabled={busy} onClick={() => sendText('', 'solve', fragment.slice(7))}>核对原提交</button></section> : archive || image ? <>{archive ? <ArchiveReplay index={Number(hash.split('/')[1] ?? 1)-1}/> : service ? <ImageQuestion hash={hash} initialInput={input} sampleUrl="/dashboard-assets/workbench/examples/linear-equation.png"/> :
      <section className="content conversation image-view"><h1>题图示例</h1>
        <p>此预览只展示示例。请打开本机 MathAgent 工作台上传 PNG 题图并求解。</p>
        <img src="/examples/linear-equation.png" alt="示例题图：解方程 3x = 12" style={{maxWidth:'100%',height:'auto'}}/>
      </section>}
      <div className="content subview-footer"><Button variant="ghost" size="sm" icon={<Plus size={15}/>} onClick={() => home()}>新建题目</Button></div></>
    : !active ? <section className="home content">
      <div className="dt-page-icon"><FunctionSquare size={26} strokeWidth={1.6}/></div><h1 className="dt-page-title">今天想解哪道题？</h1>
      <Composer busy={busy} input={input} change={s => { setInput(s); setError('') }} submit={submit} openImage={() => navigate('image')} />
      {error && <p role="alert" className="error">{error}</p>}
      <h2 className="suggest-heading">{service ? '从模拟示例开始' : '从示例开始'}</h2><div className="suggestions">{starters.map(e => <button key={e.title} onClick={() => home(e.question)}><span>{e.subject}</span>{e.title}<ArrowUpRight size={15}/></button>)}</div>
    </section> : <section className="conversation content"><div className="question">{example?.question ?? triangleQuestion}</div><div className="speaker"><span className="brand-mark"><Sigma size={15}/></span>MathAgent<span>{!example ? '等待补充' : finished ? '模拟答复' : '模拟求解中'}</span></div>
      {!example ? <TriangleClarification onAnswer={(b,h) => updateActive({example:triangleResult(b,h)})}/> : <>
        {finished && <AssistantResponse example={example} mode={active.mode}/>}
        <Progress key={active.id} example={example} completed={completed} paused={paused} onPlayback={() => {
          if (finished) { updateActive({completed:0}); setPaused(false) } else setPaused(!paused)
        }}/>
        <div className="task-actions">{parent && <button onClick={() => reopen(parent)}><GitBranch size={15}/>回看原题</button>}
          {finished && example.variant && <button onClick={openVariant}><GitBranch size={15}/>{child ? '查看关联变式' : '改为两个不同实根'}</button>}</div>
      </>}
      <Button variant="ghost" size="sm" icon={<Plus size={15}/>} onClick={() => home()}>新建题目</Button>
    </section>}
    </main><Dialog open={drawer} title="工作台导航" closeLabel="关闭导航" className="side-drawer nav-drawer" onClose={() => setDrawer(false)}>{drawer && side}</Dialog>
  </div>
}
