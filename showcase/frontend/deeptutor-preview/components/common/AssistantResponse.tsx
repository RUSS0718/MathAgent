// Adapted from DeepTutor AssistantResponse. Only public fixture text and math are rendered.
import katex from 'katex'
import { ShieldCheck } from 'lucide-react'
import type { Example } from '@/lib/examples'
function Formula({ value }: { value: string }) {
  return <span dangerouslySetInnerHTML={{ __html: katex.renderToString(value, { trust: false, throwOnError: true }) }} />
}
export function AssistantResponse({ example }: { example: Example }) {
  return <div role="article" aria-live="polite" aria-atomic="false" lang="zh-CN" className="answer">
    <h2>解题过程</h2><p>{example.method}</p><p><Formula value={example.formula} /></p>
    <h2>最终答案</h2><p className="result"><Formula value={example.answer} /></p>
    <p className="check"><ShieldCheck size={16} />{example.check}</p><small>{example.scope}</small>
  </div>
}
