import { useRef, useState } from 'react'
import { RoleAtlas, roles } from './RoleAtlas'
import { Network, List, PanelRightOpen } from 'lucide-react'
import { ActivityRow } from './activity/ActivityRow'
import { ActivityStack } from './activity/ActivityStack'
import { Dialog } from '@/shared/ui/Dialog'
import { stepsFor, type Example } from '@/lib/examples'

export function Progress({ example, completed, paused, onPlayback }: { example: Example; completed: number; paused: boolean; onPlayback: () => void }) {
  const expandedDialog = useRef<HTMLDialogElement>(null)
  const [expanded, setExpanded] = useState(false)
  const [list, setList] = useState(false)
  const [selected, select] = useState('')
  const [message, inspectMessage] = useState<number | null>(null)
  const [question, ask] = useState<number | null>(null)
  const followUp = question === null ? undefined : example.followUps?.[question]
  const steps = stepsFor(example)
  const current = steps[completed]
  const published = steps.slice(0, completed)
  const statusOf = (id: string) => current?.role === id ? '进行中' : published.some(step => step.role === id) ? '已完成' : '未参与'
  const [inspected, inspect] = useState<number | null>(null)
  function openRole(id: string, index: number | null = null) { inspect(index); select(id) }
  const summaries = published.filter((step,i) => step.role === selected && (inspected === null || i === inspected))
  const roleName = roles.find(role => role[0] === selected)?.[1]
  const details = (<Dialog open={!!selected} onClose={() => select('')} closeLabel="关闭详情" title={(roleName ?? '')+' · 阶段成果'} className="side-drawer" description="模拟运行 · 公开摘要">
      <h3>{inspected === null ? statusOf(selected) : inspected < completed ? '已完成' : '进行中'}</h3>
      {summaries.length ? summaries.map(step => <p key={step.label}>{step.note}</p>) : <p>当前没有已发布的阶段成果。</p>}
      {selected === 'step_verifier' && completed === steps.length && <p>{example.scope}</p>}
    </Dialog>)
  // The atlas caption describes the active step before its result is published.
  const atlasSteps = completed === example.review?.revision
    ? steps.map((step, i) => i === completed ? { ...step, note: '修正待发布' } : step)
    : steps
  const atlasProps = { selected, select: openRole, statusOf, steps: atlasSteps, completed, paused, onPlayback: () => { if (!current) { inspectMessage(null); ask(null) }; onPlayback() },
    scripted: Boolean(example.script), review: example.review, highlight: followUp && steps[followUp.step]?.role,
    inspected: message, inspect: inspectMessage }
  return <section className="progress-area" aria-label="求解进展">
    {!current && example.followUps && <section className="step-questions" aria-label="步骤追问"><h2>针对这一步追问</h2>
      <div>{example.followUps.map((item, i) => <button key={item.question} type="button" aria-pressed={question === i} onClick={() => {
        ask(i); setList(false); inspectMessage(example.script && item.step < steps.length - 1 ? item.step + 1 : null)
      }}>{item.question}</button>)}</div>
      {followUp && <p aria-live="polite"><strong>{steps[followUp.step].label}</strong>{followUp.answer}</p>}</section>}
    <header className="progress-header"><h2>求解进展</h2><span aria-live="polite">{completed} / {steps.length} 步完成</span></header>
    <div className="switcher"><button aria-pressed={!list} onClick={() => setList(false)}><Network size={15}/>协作星图</button>
      <button aria-pressed={list} onClick={() => setList(true)}><List size={15}/>关键进展</button></div>
    {list ? <ActivityStack>{steps.slice(0, completed + 1).map((step, i) => <ActivityRow key={step.label}
      state={i === completed ? 'running' : 'done'} title={step.label} detail={i < completed ? '已完成' : '进行中'}>
      <p>{i < completed ? step.note : '正在执行此步骤。'}</p><button className="detail-link" onClick={() => openRole(step.role, i)}><PanelRightOpen size={14}/>阶段成果</button>
    </ActivityRow>)}</ActivityStack> : <RoleAtlas {...atlasProps} expanded={false} toggle={() => {
      expandedDialog.current?.showModal()
      setExpanded(true)
    }} />}
    <dialog ref={expandedDialog} aria-label="协作星图" className="atlas-dialog" onClose={() => setExpanded(false)}
      onKeyDown={event => {
        if (event.key === 'Escape' && selected) {
          event.preventDefault()
          event.stopPropagation()
          select('')
        }
      }}>
      {expanded && <><RoleAtlas {...atlasProps} expanded toggle={() => expandedDialog.current?.close()} />{details}</>}
    </dialog>
    {!expanded && details}
  </section>
}
