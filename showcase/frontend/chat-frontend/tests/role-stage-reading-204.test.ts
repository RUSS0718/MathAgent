import assert from 'node:assert/strict'
import test from 'node:test'
import { isRef } from 'vue'
import { useRoleStageReading } from '../src/runtime/jobs/role-stage-reading.ts'
import type { RoleStage } from '../src/api/role-stage.schemas.ts'

function stage(job = 'A', role = 'planner', source = 'one'): RoleStage {
  return { version: 'role-stage-v1', job_id: job, role, status: 'running', content_status: 'published', results: [{
    source_ref: source, plan_version: 1, attempt_index: 1, stage: 'planning', body_version: source,
    validity: 'current', check: { scope: 'plan_structure', body_version: source },
    items: [{ label: 'S1', title: '结论', objective: '对所有实数 x，x² ≥ 0', depends_on: [] }],
  }] }
}

test('frozen interface restores body, expansion and scroll in the same reading context', async () => {
  const calls: unknown[] = []
  const reading = useRoleStageReading(async (job, role, source) => {
    calls.push([job, role, source])
    return stage(job, role, source)
  })
  for (const name of ['context', 'content', 'loading', 'failed', 'pendingSource', 'expanded', 'scrollTop', 'isOpen'] as const) {
    assert.ok(isRef(reading[name]), name)
  }
  await reading.open({ jobId: 'A', role: 'planner' })
  reading.expanded.value.add('extra')
  reading.scrollTop.value = 420
  reading.close()
  await reading.open({ jobId: 'A', role: 'planner' })
  assert.equal(reading.content.value?.results[0]?.body_version, 'one')
  assert.ok(reading.expanded.value.has('extra'))
  assert.equal(reading.scrollTop.value, 420)
  assert.ok(reading.isOpen.value)
  assert.ok(calls.length >= 1)
})

test('history and current caches stay separate and explicit update leaves history', async () => {
  let current = 'one'
  const reading = useRoleStageReading(async (job, role, source) => stage(job, role, source ?? current))
  await reading.open({ jobId: 'A', role: 'planner' })
  reading.scrollTop.value = 80
  await reading.selectHistory('old')
  reading.scrollTop.value = 230
  await reading.showCurrent()
  assert.equal(reading.content.value?.results[0]?.source_ref, 'one')
  assert.equal(reading.scrollTop.value, 80)
  await reading.selectHistory('old')
  assert.equal(reading.scrollTop.value, 230)
  current = 'two'
  await reading.notify('two')
  await reading.update()
  assert.equal(reading.context.value?.historical, undefined)
  assert.equal(reading.context.value?.source, undefined)
  assert.equal(reading.content.value?.results[0]?.source_ref, 'two')
  assert.equal(reading.pendingSource.value, undefined)
  await reading.selectHistory('old')
  assert.equal(reading.scrollTop.value, 230)
  assert.equal(reading.content.value?.results[0]?.source_ref, 'old')
})

function deferred() {
  return Promise.withResolvers<RoleStage>()
}

test('retry after failed explicit update retries the update rather than only validating old body', async () => {
  let fail = false
  let current = 'one'
  const reading = useRoleStageReading(async (job, role, source) => {
    if (fail) throw new Error('temporary read failure')
    return stage(job, role, source ?? current)
  })
  await reading.open({ jobId: 'A', role: 'planner' })
  current = 'two'
  fail = true
  await reading.update()
  assert.equal(reading.failed.value, true)
  assert.equal(reading.content.value?.results[0]?.source_ref, 'one')
  fail = false
  await reading.retry()
  assert.equal(reading.content.value?.results[0]?.source_ref, 'two')
  assert.equal(reading.failed.value, false)
})

test('latest authority wins and absent or mismatched authority marks frozen content unconfirmed', async () => {
  const old = deferred()
  const newer = deferred()
  const queue = [Promise.resolve(stage()), old.promise, newer.promise]
  const reading = useRoleStageReading(async () => queue.shift()!)
  await reading.open({ jobId: 'A', role: 'planner' })
  const first = reading.notify('two')
  const last = reading.notify('three')
  const replaced = stage()
  replaced.results[0]!.validity = 'replaced'
  newer.resolve(replaced)
  await last
  old.resolve(stage())
  await first
  assert.equal(reading.content.value?.results[0]?.validity, 'replaced')
  assert.equal(reading.pendingSource.value, 'three')

  for (const wrong of [stage('B'), stage('A', 'reasoner'), stage('A', 'planner', 'wrong'), { ...stage(), results: [] }]) {
    const check = useRoleStageReading(async (_job, _role, source) => source ? wrong : stage())
    await check.open({ jobId: 'A', role: 'planner' })
    await check.notify()
    assert.equal(check.failed.value, true)
    assert.equal(check.content.value?.results[0]?.body_version, 'one')
  }
})

test('initial load and retry stay distinct from successful empty content', async () => {
  const response = deferred()
  let first = true
  const reading = useRoleStageReading(async () => {
    if (first) { first = false; return response.promise }
    return { ...stage(), results: [] }
  })
  const load = reading.open({ jobId: 'A', role: 'planner' })
  assert.equal(reading.loading.value, true)
  assert.equal(reading.content.value, null)
  assert.equal(reading.failed.value, false)
  response.reject(new Error('offline'))
  await load
  assert.equal(reading.loading.value, false)
  assert.equal(reading.failed.value, true)
  await reading.retry()
  assert.equal(reading.failed.value, false)
  assert.deepEqual(reading.content.value?.results, [])
})

test('notification during first body read refreshes its authority once the body arrives', async () => {
  const initial = deferred()
  const reading = useRoleStageReading(async (job, role, source) => {
    if (!source) return initial.promise
    const authority = stage(job, role, source)
    authority.results[0]!.validity = 'replaced'
    return authority
  })
  const opened = reading.open({ jobId: 'A', role: 'planner' })
  await reading.notify('two')
  initial.resolve(stage())
  await opened
  assert.equal(reading.content.value?.results[0]?.validity, 'replaced')
  assert.equal(reading.content.value?.results[0]?.body_version, 'one')
  assert.equal(reading.pendingSource.value, 'two')
})

test('late authority failures cannot taint another task or resurrect a closed reading', async () => {
  const late = deferred()
  const reading = useRoleStageReading(async (job, role, source) => source ? late.promise : stage(job, role))
  await reading.open({ jobId: 'A', role: 'planner' })
  const notify = reading.notify('two')
  await reading.open({ jobId: 'B', role: 'reasoner' })
  late.reject(new Error('late authority failure'))
  await notify
  assert.equal(reading.context.value?.jobId, 'B')
  assert.equal(reading.failed.value, false)
  assert.equal(reading.pendingSource.value, undefined)
  reading.close()
  await reading.notify('three')
  assert.equal(reading.isOpen.value, false)
})

test('late success and failure cannot cross jobs, roles, sources or a close/reopen generation', async () => {
  for (const target of [
    { jobId: 'B', role: 'planner' },
    { jobId: 'A', role: 'reasoner' },
    { jobId: 'A', role: 'planner', source: 'old', historical: true },
    { jobId: 'A', role: 'planner' },
  ]) {
    for (const rejects of [false, true]) {
      const late = deferred()
      let first = true
      const reading = useRoleStageReading(async (job, role, source) => {
        if (first) { first = false; return late.promise }
        return stage(job, role, source ?? 'new')
      })
      const abandoned = reading.open({ jobId: 'A', role: 'planner' })
      if (target.jobId === 'A' && target.role === 'planner' && !target.source) reading.close()
      await reading.open(target)
      const before = reading.content.value
      if (rejects) late.reject(new Error('late failure'))
      else late.resolve(stage('A', 'planner', 'late'))
      await abandoned
      assert.equal(reading.content.value, before)
      assert.equal(reading.failed.value, false)
      assert.equal(reading.loading.value, false)
      reading.close()
      await reading.open(target)
      assert.equal(reading.content.value?.results[0]?.source_ref, target.source ?? 'new')
    }
  }
})

test('failed validity retry preserves existing body and reading position', async () => {
  let fail = false
  const reading = useRoleStageReading(async (job, role, source) => {
    if (fail) throw new Error('unreachable')
    const result = stage(job, role, source ?? 'two')
    if (source) result.results[0]!.items[0]!.objective = 'changed server text'
    return result
  })
  await reading.open({ jobId: 'A', role: 'planner', source: 'one', historical: true })
  const body = reading.content.value?.results[0]?.items
  reading.scrollTop.value = 420
  reading.expanded.value.add('extra')
  fail = true
  await reading.notify('two')
  assert.equal(reading.failed.value, true)
  assert.equal(reading.content.value?.results[0]?.items, body)
  fail = false
  await reading.retry()
  assert.equal(reading.failed.value, false)
  assert.equal(reading.content.value?.results[0]?.items, body)
  assert.equal(reading.scrollTop.value, 420)
  assert.ok(reading.expanded.value.has('extra'))
  assert.equal(reading.pendingSource.value, 'two')
})

test('historical missing source stays exact and never silently falls back to current', async () => {
  const sources: (string | undefined)[] = []
  const reading = useRoleStageReading(async (job, role, source) => {
    sources.push(source)
    if (source === '') throw new Error('unreconstructable')
    return stage(job, role, source)
  })
  await reading.open({ jobId: 'A', role: 'planner', historical: true })
  assert.equal(reading.content.value, null)
  assert.equal(reading.failed.value, true)
  await reading.retry()
  assert.deepEqual(sources, ['', ''])
  await reading.showCurrent()
  assert.equal(reading.failed.value, false)
  assert.equal(reading.content.value?.results[0]?.source_ref, 'one')
})

test('multiple results refresh validity independently while keeping complete body and check bindings', async () => {
  const saved = stage()
  saved.results = ['one', 'two', 'three', 'four'].map(source => stage('A', 'planner', source).results[0]!)
  const before = structuredClone(saved)
  const reading = useRoleStageReading(async (job, role, source) => {
    if (!source) return saved
    const authority = stage(job, role, source)
    if (source === 'one') authority.results[0]!.validity = 'replaced'
    authority.results[0]!.check.body_version = 'must not replace check'
    return authority
  })
  await reading.open({ jobId: 'A', role: 'planner' })
  assert.deepEqual([...reading.expanded.value], ['two', 'three', 'four'])
  reading.expanded.value.add('one')
  reading.scrollTop.value = 300
  await reading.notify()
  assert.equal(reading.pendingSource.value, undefined)
  assert.deepEqual(reading.content.value?.results.map(item => item.validity), ['replaced', 'current', 'current', 'current'])
  assert.deepEqual(reading.content.value?.results.map(item => item.check.body_version), ['one', 'two', 'three', 'four'])
  assert.equal(reading.scrollTop.value, 300)
  assert.equal(reading.expanded.value.size, 4)
  assert.deepEqual(saved, before)
})

test('body responses must match requested job, role and historical source', async () => {
  for (const wrong of [stage('B'), stage('A', 'reasoner'), stage('A', 'planner', 'wrong')]) {
    const reading = useRoleStageReading(async () => wrong)
    await reading.open({ jobId: 'A', role: 'planner', source: 'one' })
    assert.equal(reading.failed.value, true)
    assert.equal(reading.content.value, null)
  }
})

test('late explicit update cannot overwrite the newer explicit update or its error state', async () => {
  for (const rejects of [false, true]) {
    const late = deferred()
    const responses = [Promise.resolve(stage()), late.promise, Promise.resolve(stage('A', 'planner', 'three'))]
    const reading = useRoleStageReading(async () => responses.shift()!)
    await reading.open({ jobId: 'A', role: 'planner' })
    const old = reading.update()
    await reading.update()
    if (rejects) late.reject(new Error('late failure'))
    else late.resolve(stage('A', 'planner', 'two'))
    await old
    assert.equal(reading.content.value?.results[0]?.source_ref, 'three')
    assert.equal(reading.failed.value, false)
    assert.equal(reading.loading.value, false)
  }
})

test('successful current update consumes the old notification even when its result was superseded', async () => {
  let current = 'one'
  const reading = useRoleStageReading(async (job, role, source) => stage(job, role, source ?? current))
  await reading.open({ jobId: 'A', role: 'planner' })
  await reading.notify('two')
  current = 'three'
  await reading.update()
  assert.equal(reading.content.value?.results[0]?.source_ref, 'three')
  assert.equal(reading.pendingSource.value, undefined)
})

test('saved-source notification only refreshes exact-source validity until explicit update', async () => {
  let saved = false
  const calls: (string | undefined)[] = []
  const reading = useRoleStageReading(async (job, role, source) => {
    calls.push(source)
    const result = stage(job, role, source ?? (saved ? 'two' : 'one'))
    if (saved && source === 'one') {
      result.results[0]!.validity = 'replaced'
      result.results[0]!.items[0]!.objective = 'must not replace frozen body'
    }
    return result
  })
  await reading.open({ jobId: 'A', role: 'planner' })
  reading.expanded.value.add('extra')
  reading.scrollTop.value = 420
  saved = true
  await reading.notify('two')
  assert.equal(reading.pendingSource.value, 'two')
  assert.equal(reading.content.value?.results[0]?.validity, 'replaced')
  assert.equal(reading.content.value?.results[0]?.items[0]?.objective, '对所有实数 x，x² ≥ 0')
  assert.equal(reading.content.value?.results[0]?.body_version, 'one')
  assert.equal(reading.scrollTop.value, 420)
  assert.ok(reading.expanded.value.has('extra'))
  assert.deepEqual(calls, [undefined, 'one'])
  await reading.update()
  assert.equal(reading.content.value?.results[0]?.body_version, 'two')
  assert.equal(reading.pendingSource.value, undefined)
})
