'use client'
import { Moon, Sun } from 'lucide-react'
import { themeKey } from '@/lib/theme'

export function ThemeToggle() {
  function toggle() {
    const classes = document.documentElement.classList
    const dark = classes.contains('theme-snow')
    classes.replace(dark ? 'theme-snow' : 'dark', dark ? 'dark' : 'theme-snow')
    try { localStorage.setItem(themeKey, dark ? 'dark' : 'light') } catch { /* Storage may be disabled. */ }
  }
  return <button type="button" className="theme-toggle" onClick={toggle}>
    <span className="to-dark" title="切换到深色模式"><Moon size={17} aria-hidden/><span className="sr-only">切换到深色模式</span></span>
    <span className="to-light" title="切换到浅色模式"><Sun size={17} aria-hidden/><span className="sr-only">切换到浅色模式</span></span>
  </button>
}
