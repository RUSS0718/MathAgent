import { Maximize2, Minimize2, Orbit } from 'lucide-react'
import { useId } from 'react'
import type { DemoStep, Example } from '@/lib/examples'
import { ThemeToggle } from './ThemeToggle'
import './role-atlas.css'

// Coordinates from the MathAgent workbench's AgentConstellation.
const roles = [
  ['controller', '任务协调', 500, 306], ['explore', '问题探索', 234, 175],
  ['planner', '规划', 500, 90], ['reasoner', '推理', 766, 175],
  ['step_verifier', '步骤校验', 831, 365], ['whole_solution_verifier', '整体校验', 648, 518],
  ['final_generator', '终稿生成', 352, 518], ['meta', '元策略', 169, 365],
  ['researcher', '资料研究', 500, 610],
] as const
export { roles }
// A fixed star field keeps the same landmarks across renders and playback.
function makeStars() {
  let seed = 83
  const next = () => { seed = seed * 16807 % 2147483647; return seed / 2147483647 }
  return Array.from({length: 145}, () => ({ x: next()*100, y: next()*100, r: next()*0.85+0.35, opacity: next()*0.45+0.16 }))
}
const stars = makeStars()

interface AtlasProps {
  steps: DemoStep[]
  completed: number
  paused: boolean
  onPlayback: () => void
  scripted: boolean
  expanded: boolean
  toggle: () => void
  select: (id: string) => void
  selected: string
  statusOf: (role: string) => string
  review: Example['review']
  highlight?: string
  inspected: number | null
  inspect: (value: number | null) => void
}

export function RoleAtlas({ expanded, toggle, select, selected, statusOf, steps, completed, paused, onPlayback, scripted, review, highlight, inspected, inspect }: AtlasProps) {
  const marker = useId()
  const current = steps[completed]
  const previousRole = roles.find(r => r[0] === steps[completed-1]?.role)
  const currentRole = roles.find(r => r[0] === current?.role)
  const lastMessage = Math.min(completed, steps.length - 1)
  const defaultMessage = current ? completed : review ? review.challenge + 1 : lastMessage
  const message = inspected ?? defaultMessage
  const step = steps[message]
  const from = roles.find(([id]) => id === steps[message - 1]?.role)
  const to = roles.find(([id]) => id === step?.role)
  const action = step?.incoming ?? { kind: 'handoff', label: '交接' }
  const route = from && to ? from[1]+' → '+to[1] : ''
  const inFlight = !!current && message === completed
  const comparing = review && (action.kind === 'challenge' || action.kind === 'rollback')
  let path = '', midX = 0, midY = 0
  if (from && to && (scripted || current)) {
    const [, , x, y] = from, [, , tx, ty] = to
    const cx = (x + tx) / 2 - (ty - y) * 0.18
    const cy = (y + ty) / 2 + (tx - x) * 0.18
    path = `M ${x} ${y} Q ${cx} ${cy} ${tx} ${ty}`
    midX = (x + 2 * cx + tx) / 4
    midY = (y + 2 * cy + ty) / 4
  }
  return <div className="atlas" data-scripted={scripted} data-paused={paused} data-kind={action.kind}>
    <div className="atlas-head">
      <span><Orbit size={17} aria-hidden />协作星图</span>
      <div className="atlas-controls">{expanded && <ThemeToggle />}{scripted && <button type="button" onClick={onPlayback}>{!current ? '重新播放' : paused ? '继续演示' : '暂停演示'}</button>}
      <button type="button" onClick={toggle} aria-haspopup={expanded ? undefined : 'dialog'}>
        {expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}{expanded ? '收起星图' : '展开星图'}
      </button></div>
    </div>
    <div className="atlas-sky" role="group" aria-label="智能体协作星图">
      <svg className="atlas-stars" aria-hidden="true">{stars.map((s,i) =>
        <circle key={i} cx={s.x+'%'} cy={s.y+'%'} r={s.r} opacity={s.opacity} />)}</svg>
      <svg className="atlas-orbits" viewBox="0 0 1000 700" preserveAspectRatio="none" aria-hidden="true">
        {[150,245,330].map(r => <ellipse key={r} cx="500" cy="350" rx={r*1.3} ry={r} transform="rotate(-12 500 350)" />)}
      </svg>
      {path && <svg className="atlas-wire" viewBox="0 0 1000 700" preserveAspectRatio="none" aria-hidden="true">
        <defs><marker id={marker} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="userSpaceOnUse"><path d="M0 0 L8 4 L0 8Z" fill="var(--message-color)" /></marker></defs>
        <path className="atlas-link" d={path} markerEnd={'url(#'+marker+')'} />
        {scripted && <path className="atlas-hit" d={path} onClick={() => inspect(message)} />}
        {inFlight && <circle key={completed} className="atlas-packet" r="4.5" style={{offsetPath:'path("'+path+'")'}} />}
      </svg>}
      {scripted && path && <button type="button" className="atlas-edge-label" style={{left:midX/10+'%',top:midY/7+'%'}}
        aria-label={action.label+' · '+route} aria-expanded={inspected === message} onClick={() => inspect(message)}>{action.label}</button>}
      {roles.map(([id,label,x,y]) => {
        const status = statusOf(id)
        return <button key={id} type="button" className="atlas-node" style={{left:x/10+'%',top:y/7+'%'}}
          data-status={status} data-highlight={highlight === id || undefined} aria-pressed={selected === id} aria-label={'查看'+label+'阶段成果'} aria-description={status}
          onClick={() => select(id)}><i aria-hidden="true">{inFlight && path && id === to?.[0] && <span key={completed} className="atlas-arrival" />}</i><strong>{label}</strong><small>{status}</small></button>
      })}
    </div>
    {scripted && <div className="atlas-caption" role="status">
      <small>{Math.min(completed+1,steps.length)} / {steps.length}</small>
      <strong>{current ? (previousRole ? previousRole[1]+' → ' : '') + currentRole?.[1] + ' · ' + current.label : '终稿生成 · 演示完成'}</strong>
      {current && <p>{current.note}</p>}
    </div>}
    {scripted && lastMessage > 0 && <div className="atlas-records">
      <label>交接记录 <select aria-label="选择交接记录" value={inspected ?? ''} onChange={e => inspect(e.target.value ? Number(e.target.value) : null)}>
        <option value="">{current ? '跟随演示' : '选择一条交接'}</option>
        {steps.slice(1, lastMessage + 1).map((s, i) => <option key={s.label} value={i+1}>{i+1}. {s.incoming?.label ?? '交接'} · {steps[i].label}</option>)}
      </select></label>
      <div className="edge-legend" aria-label="连线图例"><span>送审</span><span>质疑</span><span>退回</span><span>通过</span></div>
    </div>}
    {inspected !== null && step && from && <section className="decision-evidence" aria-label="决策依据">
      <header><strong>{action.label} · {route}</strong><button type="button" onClick={() => inspect(null)} aria-label="关闭决策依据">收起</button></header>
      {comparing ? <dl><dt>候选区间</dt><dd>{steps[review.candidate].note}</dd>
        <dt>反例</dt><dd>{steps[review.challenge].note}</dd><dt>修正结果</dt>
        <dd>{completed > review.revision ? steps[review.revision].note : '修正待发布'}</dd></dl>
        : <p>{steps[message-1].note}</p>}
    </section>}
    <div className="atlas-legend" aria-label="状态图例"><span>进行中</span><span>已完成</span><span>未参与</span></div>
  </div>
}
