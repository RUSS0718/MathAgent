import { ref, shallowRef } from 'vue'
import type { RoleStage } from '../../api/role-stage.schemas.ts'

export interface RoleStageReadingContext {
  jobId: string
  role: string
  source?: string
  historical?: boolean
}

type Loader = (jobId: string, role: string, source?: string) => Promise<RoleStage>

const defaultLoader: Loader = async (job, role, source) => {
  const { api } = await import('../../api/client.ts')
  return api.roleResults(job, role, source)
}

export function useRoleStageReading(loader: Loader = defaultLoader) {
  const context = shallowRef<RoleStageReadingContext | null>(null)
  const content = shallowRef<RoleStage | null>(null)
  const loading = ref(false)
  const failed = ref(false)
  const pendingSource = ref<string>()
  const expanded = ref(new Set<string>())
  const scrollTop = ref(0)
  const isOpen = ref(false)
  type RetryMode = 'body' | 'validity' | 'update'
  const cache = new Map<string, { content: RoleStage | null; failed: boolean; pendingSource?: string; expanded: Set<string>; scrollTop: number; retryMode: RetryMode }>()
  let retryMode: RetryMode = 'body'
  let generation = 0
  let bodyRequest = 0
  let validityRequest = 0
  let notification = 0

  function key(value: RoleStageReadingContext) {
    return JSON.stringify([value.jobId, value.role, value.historical || value.source !== undefined ? ['source', value.source ?? ''] : ['current']])
  }

  function save() {
    if (context.value) cache.set(key(context.value), {
      content: content.value, failed: failed.value, pendingSource: pendingSource.value,
      expanded: new Set(expanded.value), scrollTop: scrollTop.value, retryMode,
    })
  }

  async function read(current = false) {
    const selected = context.value
    if (!selected || !isOpen.value) return
    const epoch = generation
    const request = ++bodyRequest
    const lastNotification = notification
    const pending = pendingSource.value
    validityRequest++
    loading.value = true
    try {
      const source = current ? undefined : selected.historical ? selected.source ?? '' : selected.source
      const result = await loader(selected.jobId, selected.role, source)
      if (epoch !== generation || request !== bodyRequest) return
      if (result.job_id !== selected.jobId || result.role !== selected.role ||
        (source !== undefined && result.results.some(item => item.source_ref !== source))) throw new Error('Mismatched reading context')
      if (current && (selected.historical || selected.source !== undefined)) {
        save()
        context.value = { jobId: selected.jobId, role: selected.role }
      }
      content.value = result
      expanded.value = new Set(result.results.slice(-3).map(item => item.source_ref))
      scrollTop.value = 0
      failed.value = false
      if ((current && pendingSource.value === pending) || result.results.some(item => item.source_ref === pendingSource.value)) pendingSource.value = undefined
      // A save may arrive before the initial body; do not lose its validity refresh.
      if (notification !== lastNotification) await notify()
    } catch {
      if (epoch === generation && request === bodyRequest) {
        failed.value = true
        retryMode = current ? 'update' : 'body'
      }
    } finally {
      if (epoch === generation && request === bodyRequest) loading.value = false
    }
  }

  async function notify(source?: string) {
    const selected = context.value
    const body = content.value
    if (!selected || !isOpen.value) return
    notification++
    if (source && !body?.results.some(item => item.source_ref === source)) pendingSource.value = source
    if (!body?.results.length) return
    const epoch = generation
    const request = ++validityRequest
    try {
      const responses = await Promise.all(body.results.map(item => loader(selected.jobId, selected.role, item.source_ref)))
      if (epoch !== generation || request !== validityRequest || content.value !== body) return
      const results = body.results.map((item, index) => {
        const response = responses[index]
        const authority = response?.results.find(candidate => candidate.source_ref === item.source_ref && candidate.body_version === item.body_version)
        if (response?.job_id !== selected.jobId || response.role !== selected.role || !authority) throw new Error('Unconfirmed source')
        return { ...item, validity: authority.validity }
      })
      content.value = { ...body, results }
      failed.value = false
    } catch {
      if (epoch === generation && request === validityRequest && content.value === body) {
        failed.value = true
        retryMode = 'validity'
      }
    }
  }

  async function open(selected: RoleStageReadingContext) {
    save()
    generation++
    context.value = { ...selected }
    isOpen.value = true
    loading.value = false
    const saved = cache.get(key(selected))
    content.value = saved?.content ?? null
    failed.value = saved?.failed ?? false
    retryMode = saved?.retryMode ?? 'body'
    pendingSource.value = saved?.pendingSource
    expanded.value = new Set(saved?.expanded)
    scrollTop.value = saved?.scrollTop ?? 0
    if (!content.value) await read()
    else await notify()
  }

  function close() {
    save()
    generation++
    isOpen.value = false
    loading.value = false
  }

  async function selectHistory(source: string) {
    if (context.value) await open({ jobId: context.value.jobId, role: context.value.role, source, historical: true })
  }

  async function showCurrent() {
    if (context.value) await open({ jobId: context.value.jobId, role: context.value.role })
  }

  return { context, content, loading, failed, pendingSource, expanded, scrollTop, isOpen,
    open, close, retry: () => retryMode === 'validity' ? notify() : read(retryMode === 'update'),
    selectHistory, showCurrent, update: () => read(true), notify }
}
