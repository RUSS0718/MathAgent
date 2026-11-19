import { useState } from 'react'
import { Network, List, PanelRightOpen } from 'lucide-react'
import { ActivityRow } from './activity/ActivityRow'
import { ActivityStack } from './activity/ActivityStack'
import { Dialog } from '@/shared/ui/Dialog'
import type { Example } from '@/lib/examples'

// Coordinates from the MathAgent workbench's AgentConstellation.
const roles = [
  ['controller', '任务协调', 500, 306], ['explore', '问题探索', 234, 175],
  ['planner', '规划', 500, 90], ['reasoner', '推理', 766, 175],
  ['step_verifier', '步骤校验', 831, 365], ['whole_solution_verifier', '整体校验', 648, 518],
  ['final_generator', '终稿生成', 352, 518], ['meta', '元策略', 169, 365],
  ['researcher', '资料研究', 500, 610],
] as const
export function Progress({ example, completed }: { example: Example; completed: number }) {
  const [list, setList] = useState(false)
  const [selected, select] = useState('')
  const steps = [
    { role: 'planner', label: '制定求解计划', note: '确定求解方法，最后用题目给定的条件检查结果。' },
    { role: 'reasoner', label: '推导候选答案', note: example.method },
    { role: 'step_verifier', label: '检查候选结果', note: example.check },
  ]
  const stepIndex = (role: string) => steps.findIndex(step => step.role === role)
  const status = (index: number) => index < 0 || index > completed ? '未参与' : index === completed ? '进行中' : '已完成'
  const selectedIndex = stepIndex(selected)
  const roleName = roles.find(role => role[0] === selected)?.[1]
  return <section className="progress-area" aria-label="求解进展">
    <header className="progress-header"><h2>求解进展</h2><span aria-live="polite">{completed} / 3 步完成</span></header>
    <div className="switcher"><button aria-pressed={!list} onClick={() => setList(false)}><Network size={15}/>协作星图</button>
      <button aria-pressed={list} onClick={() => setList(true)}><List size={15}/>关键进展</button></div>
    {list ? <ActivityStack>{steps.slice(0, completed + 1).map((step, i) => <ActivityRow key={step.role}
      state={i === completed ? 'running' : 'done'} title={step.label} detail={status(i)}>
      <p>{i < completed ? step.note : '正在执行此步骤。'}</p><button className="detail-link" onClick={() => select(step.role)}><PanelRightOpen size={14}/>阶段成果</button>
    </ActivityRow>)}</ActivityStack> : <div className="star-map" role="group" aria-label="智能体协作星图">
      <svg aria-hidden="true" viewBox="0 0 1000 700" preserveAspectRatio="none">{[150,245,330].map(r => <ellipse key={r} cx="500" cy="350" rx={r*1.3} ry={r} />)}
        {roles.slice(1).map(([id,,x,y]) => <line key={id} x1="500" y1="306" x2={x} y2={y} />)}</svg>
      {roles.map(([id,label,x,y]) => <button key={id} style={{ left: x/10+'%', top: y/7+'%' }}
        data-status={status(stepIndex(id))} aria-label={'查看'+label+'阶段成果'} onClick={() => select(id)}>{label}<small>{status(stepIndex(id))}</small></button>)}
    </div>}
    <Dialog open={!!selected} onClose={() => select('')} closeLabel="关闭详情" title={(roleName ?? '')+' · 阶段成果'} className="side-drawer" description="模拟运行 · 公开摘要">
      <h3>{status(selectedIndex)}</h3><p>{selectedIndex >= 0 && selectedIndex < completed ? steps[selectedIndex].note : '当前没有已发布的阶段成果。'}</p>
    </Dialog>
  </section>
}
