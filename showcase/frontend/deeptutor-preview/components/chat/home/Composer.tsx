// Adapted from DeepTutor ChatComposer and ComposerInput for local math examples.
import { useRef } from 'react'
import { ArrowUp, Calculator } from 'lucide-react'
import { shouldSubmitOnEnter } from '@/lib/composer-keyboard'
import { useImeComposing } from '@/lib/use-ime-composing'
import { useAutoSizedTextarea } from '@/lib/use-auto-sized-textarea'
import styles from './ChatComposer.module.css'

export function Composer({ input, change, submit }: { input: string; change: (s: string) => void; submit: () => void }) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const { isComposingRef, onCompositionStart, onCompositionEnd } = useImeComposing()
  useAutoSizedTextarea(textareaRef, input, { min: 60, max: 180 })
  return <form className={styles.surface + ' dt-composer-surface relative rounded-[26px] border bg-[var(--card)] p-4'}
    onSubmit={event => { event.preventDefault(); submit() }}>
    <textarea ref={textareaRef} dir="auto" value={input} rows={1} maxLength={32000}
      aria-label="数学问题" placeholder="输入数学问题，或选择下方示例…" onChange={e => change(e.target.value)}
      onCompositionStart={onCompositionStart} onCompositionEnd={onCompositionEnd}
      onKeyDown={event => { if (shouldSubmitOnEnter(event, isComposingRef.current)) { event.preventDefault(); submit() } }}
      className="w-full resize-none bg-transparent px-1 outline-none" />
    <div className={styles.toolbar}><div className={styles.context}><span className="tool-mode"><Calculator size={15} />数学求解</span></div>
      <div className={styles.actions}><button className="send" title="发送" aria-label="发送" disabled={!input.trim()}><ArrowUp size={18} /></button></div>
    </div>
  </form>
}
