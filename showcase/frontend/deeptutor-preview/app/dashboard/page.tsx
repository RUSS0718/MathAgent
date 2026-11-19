'use client'
import { useEffect, useState } from 'react'
import { ArrowUpRight, Compass, FunctionSquare, History, Menu, MessageSquare, Plus, Search, Sigma, SquarePen } from 'lucide-react'
import { NavigationRow, Section } from '@/components/sidebar/NavigationPrimitives'
import { Composer } from '@/components/chat/home/Composer'
import { AssistantResponse } from '@/components/common/AssistantResponse'
import { Progress } from '@/components/Progress'
import { Button } from '@/shared/ui/Button'
import { Dialog } from '@/shared/ui/Dialog'
import { examples } from '@/lib/examples'

export default function Dashboard() {
  const [input, setInput] = useState('')
  const [error, setError] = useState('')
  const [active, setActive] = useState<number | null>(null)
  const [completed, setCompleted] = useState(0)
  const [history, setHistory] = useState<number[]>([])
  const [drawer, setDrawer] = useState(false)
  const [search, setSearch] = useState<string | null>(null)
  useEffect(() => {
    if (active === null || completed === 3) return
    const timer = window.setTimeout(() => setCompleted(completed + 1), 1250)
    return () => window.clearTimeout(timer)
  }, [active, completed])
  useEffect(() => {
    if (active !== null && completed === 3) setHistory(h => [active, ...h.filter(n => n !== active)])
  }, [active, completed])
  function home(text = '') {
    setActive(null); setCompleted(0); setInput(text); setError(''); setDrawer(false)
  }
  function submit() {
    if (!input.trim()) return
    const index = examples.findIndex(e => e.question === input.trim())
    if (index < 0) { setError('此预览仅提供下方两道示例的模拟答复。请选择一道示例。'); return }
    setActive(index); setCompleted(0); setError('')
  }
  const side = <nav aria-label="工作台导航" className="dt-product-sidebar side-content">
    <div className="brand"><span className="brand-mark"><Sigma size={18}/></span>MathAgent</div>
    <NavigationRow label="新建题目" icon={SquarePen} active={active === null} onClick={() => home()} />
    <NavigationRow label="搜索题目" icon={Search} active={search !== null} onClick={() => setSearch(search === null ? '' : null)} />
    {search !== null && <input autoFocus aria-label="搜索题目" placeholder="搜索示例和最近题目" className="search" value={search} onChange={e => setSearch(e.target.value)} />}
    <Section title="示例题库">{examples.filter(e => e.title.includes((search ?? '').trim())).map(e => <NavigationRow key={e.title} label={e.title} icon={MessageSquare} onClick={() => home(e.question)} />)}
      {search && !examples.some(e => e.title.includes(search.trim())) && <small>没有匹配的题目</small>}</Section>
    {history.length > 0 && <Section title="最近题目">{history.filter(i => examples[i].title.includes((search ?? '').trim())).map(i => <NavigationRow key={i} label={examples[i].title} icon={History} active={active === i} onClick={() => { setActive(i); setCompleted(3); setDrawer(false) }} />)}</Section>}
    <div className="side-foot"><span className="status-light"/>本地工作区</div>
  </nav>
  const example = active === null ? null : examples[active]
  return <div className="workspace"><aside className="desktop-side">{side}</aside>
    <main><header className="pagebar"><button className="mobile-menu dt-nav-icon" onClick={() => setDrawer(true)} title="打开导航" aria-label="打开导航"><Menu size={19}/></button>
      <Compass size={16}/>数学工作台<span className="separator">/</span><span>{example?.title ?? '新建题目'}</span><small className="source-label">模拟运行</small></header>
    {example === null ? <section className="home content">
      <div className="dt-page-icon"><FunctionSquare size={26} strokeWidth={1.6}/></div><h1 className="dt-page-title">今天想解哪道题？</h1>
      <Composer input={input} change={s => { setInput(s); setError('') }} submit={submit} />
      {error && <p role="alert" className="error">{error}</p>}
      <h2 className="suggest-heading">从示例开始</h2><div className="suggestions">{examples.map(e => <button key={e.title} onClick={() => home(e.question)}><span>{e.subject}</span>{e.title}<ArrowUpRight size={15}/></button>)}</div>
    </section> : <section className="conversation content"><div className="question">{example.question}</div><div className="speaker"><span className="brand-mark"><Sigma size={15}/></span>MathAgent<span>{completed === 3 ? '模拟答复' : '模拟求解中'}</span></div>
      {completed === 3 && <AssistantResponse example={example} />}<Progress key={active} example={example} completed={completed}/>
      <Button variant="ghost" size="sm" icon={<Plus size={15}/>} onClick={() => home()}>新建题目</Button>
    </section>}
    </main><Dialog open={drawer} title="工作台导航" closeLabel="关闭导航" className="side-drawer nav-drawer" onClose={() => setDrawer(false)}>{drawer && side}</Dialog>
  </div>
}
