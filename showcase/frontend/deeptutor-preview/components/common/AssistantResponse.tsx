// Adapted from DeepTutor AssistantResponse. Only public fixture text and math are rendered.
import { useState } from 'react'
import katex from 'katex'
import { downloadReport } from '@/lib/report-export'
import { ShieldCheck } from 'lucide-react'
import type { Example } from '@/lib/examples'
import { modes, type OutputMode } from '@/lib/output-modes'
function Formula({ value }: { value: string }) {
  return <span dangerouslySetInnerHTML={{ __html: katex.renderToString(value, { trust: false, throwOnError: true }) }} />
}
function reportMarkdown(example: Example): string {
  return [
    '# 求解报告 · '+example.title,
    '',
    '## 题目',
    example.question,
    '',
    '## 结论',
    '$$\n'+example.answer+'\n$$',
    '',
    '## 推导依据',
    example.method,
    '',
    '$$\n'+example.formula+'\n$$',
    '',
    '## 复核结果',
    example.check,
    '',
    '## 检查范围',
    example.scope,
    '',
    '> 本报告来自 MathAgent 本地模拟演示。',
  ].join('\n')
}

export function ReportActions({ title, markdown }: { title: string; markdown: string }) {
  const [notice, setNotice] = useState('')
  async function copy() {
    try {
      await navigator.clipboard.writeText(markdown)
      setNotice('报告已复制')
    } catch {
      setNotice('无法访问剪贴板，请使用导出 Markdown。')
    }
  }
  return <div className="report-actions" aria-label="报告操作">
    <button type="button" onClick={copy}>复制报告</button>
    <button type="button" onClick={() => downloadReport(title, markdown)}>导出 Markdown</button>
    <small role="status">{notice}</small>
  </div>
}

export function AssistantResponse({ example, mode }: { example: Example; mode: OutputMode }) {
  const solution = <><h2>解题过程</h2><p>{example.method}</p><p><Formula value={example.formula} /></p>
    <h2>最终答案</h2><p className="result"><Formula value={example.answer} /></p>
    <p className="check"><ShieldCheck size={16} />{example.check}</p><small>{example.scope}</small></>
  return <article aria-label={modes[mode]+'模拟答复'} lang="zh-CN" className={'answer skill-'+mode}>
      <div className="answer-mode"><span>/{mode}</span> {modes[mode]}</div>
      {mode === 'solve' && solution}
      {mode === 'explore' && <><h2>候选路线</h2><ol className="route-options">
        <li><strong>从题设出发</strong><p>{example.method}</p></li>
        <li><strong>换一种推导</strong><p>{example.alternative}</p></li>
      </ol><h2>如何检验</h2><p>{example.check}</p><details><summary>查看两条路线的结论</summary><Formula value={example.answer} /></details></>}
      {mode === 'report' && <><h2>求解报告 · {example.title}</h2><ReportActions title={example.title} markdown={reportMarkdown(example)} />
        <dl className="report-fields"><dt>结论</dt><dd className="result"><Formula value={example.answer} /></dd>
          <dt>推导依据</dt><dd>{example.method}<p><Formula value={example.formula} /></p></dd>
          <dt>复核结果</dt><dd>{example.check}</dd><dt>检查范围</dt><dd>{example.scope}</dd></dl></>}
      {mode === 'teach' && <><h2>先想一想</h2><p>{example.prompt}</p>
        <details><summary>展开提示</summary><p>{example.hint}</p></details>
        <details><summary>查看参考解答</summary>{solution}</details></>}
    </article>
}
