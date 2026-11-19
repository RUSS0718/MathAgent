// Adapted from DeepTutor NavigationPrimitives for local preview selections.
import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
export function NavigationRow({ label, icon: Icon, active, onClick }: {
  label: string; icon: LucideIcon; active?: boolean; onClick: () => void
}) {
  return <button type="button" onClick={onClick} aria-current={active ? 'page' : undefined}
    className={'dt-navigation-row w-full ' + (active ? 'is-active' : '')}>
    <Icon size={16} strokeWidth={1.6} /><span className="min-w-0 flex-1 truncate">{label}</span>
  </button>
}
export function Section({
  title,
  action,
  children,
}: {
  title: string
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="dt-navigation-section">
      <div className="dt-navigation-heading">
        <span>{title}</span>
        {action}
      </div>
      {children}
    </section>
  )
}
