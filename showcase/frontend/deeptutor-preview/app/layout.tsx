import type { ReactNode } from 'react'
import 'katex/dist/katex.min.css'
import './globals.css'
import '../features/ui-layout/modern/modern.css'
import './workspace.css'

export const metadata = { title: 'MathAgent · 数学工作台' }
export default function Layout({ children }: { children: ReactNode }) {
  return <html lang="zh-CN" className="theme-snow" data-ui-layout="modern"><body>{children}</body></html>
}
