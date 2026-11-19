import { ArrowLeft, ArrowRight } from 'lucide-react'

// Public excerpts of D2, docs/evals/onsite-demo-209-20261118.md (ordinary workspace).
const stages = [
  ['求出参数', '先解 2a + 1 = 7，得到唯一实数 a = 3。', 'a = 3'],
  ['使用上一步的参数', '把第一步的 a = 3 代入 x² − ax + 2 = 0，得到 x² − 3x + 2 = 0。', 'x² − 3x + 2 = 0'],
  ['交付结果', '因式分解为 (x − 1)(x − 2) = 0，全部实数解为 1 和 2。', 'x = 1 或 x = 2'],
] as const
export function ArchiveReplay({ index }: { index: number }) {
  function seek(i: number) { window.location.hash = `d2/${i+1}` }
  const [title, text, result] = stages[index]
  return <section className="content conversation archive-view"><h1>参数传递与复核</h1>
    <p className="archive-source">D2 真实历史 · 2026 年 11 月 18 日 · 公开成果摘录</p>
    <div className="question">先求出满足 2a + 1 = 7 的实数 a，再用所得的 a 解方程 x² − ax + 2 = 0，列出全部实数解并说明没有遗漏。</div>
    <section className="inline-panel" aria-label="历史成果" aria-live="polite"><small>步骤 {index+1} / {stages.length}</small><h2>{title}</h2><p>{text}</p><strong className="archive-result">{result}</strong></section>
    <div className="task-actions"><button disabled={index===0} onClick={() => seek(index-1)}><ArrowLeft size={14}/>上一步</button>
      <button disabled={index===stages.length-1} onClick={() => seek(index+1)}>下一步<ArrowRight size={14}/></button></div>
    <small className="archive-source">原任务 run_d81b65537c10122de78607d6274108c9</small></section>
}
