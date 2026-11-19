import { useState } from 'react'

export function TriangleClarification({ onAnswer }: { onAnswer: (base: number, height: number) => void }) {
  const [base, setBase] = useState('')
  const [height, setHeight] = useState('')
  const area = Number(base) * Number(height) / 2
  const valid = Number(base) > 0 && Number(height) > 0 && Number.isFinite(area) && area > 0
  return <section className="inline-panel" aria-label="补充条件"><h2>请补充三角形的底和对应的高</h2>
    <form onSubmit={e => { e.preventDefault(); if (valid) onAnswer(Number(base), Number(height)) }}>
      <div className="dimension-fields">
        <label>底（厘米）<input type="number" step="any" min="0" required value={base} placeholder="例如 6" onChange={e => setBase(e.target.value)}/></label>
        <label>对应的高（厘米）<input type="number" step="any" min="0" required value={height} placeholder="例如 4" onChange={e => setHeight(e.target.value)}/></label>
      </div><button type="submit" className="primary-action" disabled={!valid}>补充并继续</button>
    </form></section>
}
