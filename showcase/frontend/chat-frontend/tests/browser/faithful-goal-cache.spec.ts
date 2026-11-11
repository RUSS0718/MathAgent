import { expect, test } from '@playwright/test'
import { mockWorkspace } from './fixtures'

function metadata(enabled: boolean, cleared = false) {
  const entry = {
    cache_id: 'cache-demo', state: cleared ? 'invalidated' : 'active',
    reason: cleared ? 'cache_cleared' : 'current',
    created_at: '2026-11-10T01:00:00Z', updated_at: cleared ? '2026-11-10T02:00:00Z' : '2026-11-10T01:00:00Z',
    ...(cleared ? { source_run_id: 'run-demo', source_attempt_id: 'attempt-demo', source_grade: 'L2', grade_ceiling: 'L2' } : {}),
  }
  return {
    success: true, authority: 'metadata_only', enabled, entries: [entry],
    events: [
      { cache_id: 'cache-demo', event: 'receipt_admitted', created_at: '2026-11-10T01:00:00Z' },
      ...(cleared ? [{ cache_id: 'cache-demo', event: 'receipt_invalidated', details: { reason: 'cache_cleared', tombstone: true }, created_at: '2026-11-10T02:00:00Z' }, { event: 'cache_cleared', details: { tombstone: true }, created_at: '2026-11-10T02:00:01Z' }] : []),
    ],
  }
}

test('404 hides global goal-cache controls when the feature is unavailable', async ({ page }) => {
  await mockWorkspace(page)
  await page.route('**/api/sessions/session-demo/memory/**', route =>
    route.fulfill({ status: 404, json: { code: 'not_found' } }))
  await page.route('**/api/sessions/session-demo/goal-cache', route =>
    route.fulfill({ status: 404, json: { code: 'not_found' } }))
  await page.goto('/dashboard-assets/run/run-demo')
  await expect(page.getByRole('region', { name: '会话形式缓存' })).toHaveCount(0)
})

test('disabled cache can be enabled, reports busy and failed states, and shows cleared history', async ({ page }) => {
  await mockWorkspace(page)
  await page.route('**/api/sessions/session-demo/memory/**', route =>
    route.fulfill({ status: 404, json: { code: 'not_found' } }))
  let enabled = false
  let cleared = false
  let enterEnable!: () => void
  let releaseEnable!: () => void
  let enterDisable!: () => void
  let releaseDisable!: () => void
  const enableStarted = new Promise<void>(resolve => { enterEnable = resolve })
  const enableGate = new Promise<void>(resolve => { releaseEnable = resolve })
  const disableStarted = new Promise<void>(resolve => { enterDisable = resolve })
  const disableGate = new Promise<void>(resolve => { releaseDisable = resolve })
  const mutationHeaders: string[] = []
  let disableCalls = 0

  await page.route('**/api/sessions/session-demo/goal-cache', async route => {
    const request = route.request()
    if (request.method() === 'GET') return route.fulfill({ json: metadata(enabled, cleared) })
    mutationHeaders.push(request.headers()['x-csrf-token'] ?? '')
    if (request.method() === 'PUT') {
      const body = request.postDataJSON() as { enabled: boolean }
      if (body.enabled) {
        enterEnable()
        await enableGate
        enabled = true
        return route.fulfill({ json: { success: true } })
      }
      if (++disableCalls === 1) {
        enterDisable()
        await disableGate
        return route.fulfill({ status: 503, json: { error: 'temporarily unavailable' } })
      }
      enabled = false
      return route.fulfill({ json: { success: true } })
    }
    if (request.method() === 'DELETE') {
      cleared = true
      return route.fulfill({ json: { success: true } })
    }
    return route.fulfill({ status: 405 })
  })

  await page.goto('/dashboard-assets/run/run-demo')
  const panel = page.getByRole('region', { name: '会话形式缓存' })
  await expect(panel).toBeVisible()
  await expect(panel).toContainText('已停用')
  await expect(panel).toContainText('缓存元数据不是证明')
  await expect(panel.locator('dl.data-list').getByText('run-demo', { exact: true })).toHaveCount(0)
  const enable = panel.getByRole('button', { name: '启用本会话缓存' })
  await enable.click()
  await enableStarted
  await expect(enable).toBeDisabled()
  await expect(enable).toHaveAttribute('aria-busy', 'true')
  releaseEnable()
  await expect(panel).toContainText('已启用')
  await expect(panel.getByRole('button', { name: '停用本会话缓存' })).toBeVisible()

  const disable = panel.getByRole('button', { name: '停用本会话缓存' })
  await disable.click()
  await disableStarted
  await expect(disable).toBeDisabled()
  await expect(disable).toHaveAttribute('aria-busy', 'true')
  releaseDisable()
  await expect(panel.getByRole('alert')).toContainText('temporarily unavailable')
  await expect(panel).toContainText('已启用')
  await disable.click()
  await expect(panel).toContainText('已停用')
  await expect(panel.getByRole('button', { name: '启用本会话缓存' })).toBeVisible()

  page.once('dialog', async dialog => {
    expect(dialog.message()).toContain('清除')
    await dialog.accept()
  })
  await panel.getByRole('button', { name: '清除本会话缓存' }).click()
  await expect(panel).toContainText('invalidated')
  await expect(panel).toContainText('cache_cleared')
  await expect(panel).toContainText('receipt_admitted')
  await expect(panel.locator('dl.data-list').getByText('run-demo', { exact: true })).toBeVisible()
  await expect(panel.locator('dl.data-list').getByText('attempt-demo', { exact: true })).toBeVisible()
  await expect(panel.locator('dl.data-list').getByText('L2', { exact: true })).toHaveCount(2)
  expect(mutationHeaders).toEqual(['synthetic', 'synthetic', 'synthetic', 'synthetic'])
  await page.setViewportSize({ width: 390, height: 844 })
  const widths = await panel.evaluate(element => ({
    panel: element.getBoundingClientRect().width,
    content: element.scrollWidth,
    viewport: window.innerWidth,
  }))
  expect(widths.panel).toBeLessThanOrEqual(widths.viewport)
  expect(widths.content).toBeLessThanOrEqual(widths.panel + 1)
})

test('cache review exposes each recorded drift and recheck rejection reason', async ({ page }) => {
  await mockWorkspace(page)
  await page.route('**/api/sessions/session-demo/memory/**', route =>
    route.fulfill({ status: 404, json: { code: 'not_found' } }))
  const reasons = [
    'declaration_drift', 'import_dependency_drift', 'template_drift', 'axiom_policy_drift',
    'proof_identity_drift', 'dependency_audit_drift', 'lean_environment_drift',
    'goal_cache_key_drift', 'current_lean_identity_untrusted', 'lean_recheck_failed',
    'lean_proof_or_environment_drift', 'cache_cleared',
  ]
  const response = {
    ...metadata(true),
    entries: reasons.map((reason, index) => ({
      cache_id: `cache-${index}`, state: reason === 'cache_cleared' ? 'invalidated' : 'stale', reason,
      created_at: '2026-11-10T01:00:00Z', updated_at: '2026-11-10T02:00:00Z',
      source_run_id: 'run-source', source_attempt_id: `attempt-${index}`,
      source_grade: 'L2', grade_ceiling: 'L2',
    })),
    events: reasons.map((reason, index) => ({
      cache_id: `cache-${index}`,
      event: reason === 'cache_cleared' ? 'receipt_invalidated' : 'receipt_stale',
      details: { reason, tombstone: reason === 'cache_cleared' },
      created_at: '2026-11-10T02:00:00Z',
    })),
  }
  await page.route('**/api/sessions/session-demo/goal-cache', route =>
    route.fulfill({ json: response }))

  await page.goto('/dashboard-assets/run/run-demo')
  const panel = page.getByRole('region', { name: '会话形式缓存' })
  for (const reason of reasons) await expect(panel).toContainText(reason)
  await expect(panel).toContainText('invalidated')
  await expect(panel).toContainText('stale')
  await expect(panel).toContainText('run-source')
})
