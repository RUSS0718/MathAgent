export const DASHBOARD_BASE = '/dashboard'
export const DASHBOARD_ASSETS_BASE = '/dashboard-assets'
export const DASHBOARD_SETTINGS_PATH = '/dashboard/settings'
export type DashboardRoute = { view: 'workspace' | 'settings'; sessionId: string | null; path: string }
const SESSION_PATH_PATTERN = /^\/dashboard\/session\/([A-Za-z0-9._-]{1,64})$/

function normalize(pathname: string): string {
  if (!pathname || pathname === DASHBOARD_BASE || pathname === `${DASHBOARD_BASE}/`) return DASHBOARD_BASE
  if (pathname === DASHBOARD_ASSETS_BASE || pathname === `${DASHBOARD_ASSETS_BASE}/`) return DASHBOARD_BASE
  return pathname.startsWith(`${DASHBOARD_ASSETS_BASE}/`) ? `${DASHBOARD_BASE}${pathname.slice(DASHBOARD_ASSETS_BASE.length)}` : pathname
}
export function readDashboardRoute(pathname: string): DashboardRoute {
  const path = normalize(pathname)
  if (path === DASHBOARD_SETTINGS_PATH) return { view: 'settings', sessionId: null, path }
  const match = SESSION_PATH_PATTERN.exec(path)
  return match ? { view: 'workspace', sessionId: match[1]!, path } : { view: 'workspace', sessionId: null, path: DASHBOARD_BASE }
}
export function sessionHref(id: string): string { return `${DASHBOARD_BASE}/session/${id}` }
export function settingsHref(): string { return DASHBOARD_SETTINGS_PATH }
export function workspaceHref(): string { return DASHBOARD_BASE }
