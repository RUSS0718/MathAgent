import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ChatWorkspace from './components/ChatWorkspace.vue'
import { useAuthStore } from './stores/auth.store'

export async function mountSession(host: HTMLElement, id: string, signal: AbortSignal) {
  const stores = createPinia()
  const app = createApp(ChatWorkspace, { path: location.pathname, sessionId: id, embedded: true })
  app.use(stores)
  if (!await useAuthStore(stores).check()) throw new Error('本机身份尚未就绪。')
  if (signal.aborted) return
  app.mount(host)
  signal.addEventListener('abort', () => app.unmount(), { once: true })
}
