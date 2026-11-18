import { expect, test } from '@playwright/test'
import { mockWorkspace } from './fixtures'

test.describe('session time', () => {
  test.use({ timezoneId: 'UTC' })

  test('renders UTC session timestamps in Beijing time', async ({ page }) => {
    await mockWorkspace(page)
    await page.route('**/api/sessions', route => route.fulfill({ json: [[
      'session-demo', { preview: '多项式候选根验证', last_time: '2026-11-16T12:18:36.932450+00:00' },
    ]] }))
    await page.goto('/dashboard-assets/session/session-demo')
    await expect(page.locator('.session-time')).toHaveText('2026/11/16 20:18')
  })
})

test('new workspace replaces the observer and shares state across its views', async ({ page }) => {
  await mockWorkspace(page, true)
  await page.goto('/dashboard-assets/session/session-demo')
  await expect(page.locator('[data-workspace="conversation-workbench"]')).toBeVisible()
  await expect(page.locator('.workspace-shell')).toHaveCount(0)
  await page.getByRole('button', { name: '关键进展', exact: true }).click()
  const workbench = page.getByRole('region', { name: '对话式执行工作台' })
  await expect(workbench.locator('.conversation-events article')).toHaveCount(1)
  await workbench.getByRole('button', { name: '完整星图', exact: true }).click()
  await expect(workbench.locator('.constellation:not(.mini)')).toBeVisible()
  await workbench.getByRole('button', { name: '关键进展', exact: true }).click()
  await expect(workbench.locator('.conversation-events article:visible')).toHaveCount(1)
})

test('IME Enter confirms composition without sending', async ({ page }) => {
  await mockWorkspace(page)
  await page.goto('/dashboard-assets/session/session-demo')
  const input = page.getByRole('textbox', { name: '数学问题' })
  await input.fill('求解方程')
  await input.dispatchEvent('keydown', { key: 'Enter', isComposing: true })
  await expect(input).toHaveValue('求解方程')
})

test('first click collapses an expanded timeline node', async ({ page }) => {
  await mockWorkspace(page, true)
  await page.route('**/api/check_auth', r => r.fulfill({ json: { isLoggedIn: true, username: 'local', csrf_token: 'synthetic', permissions: ['reviewer.access'] } }))
  await page.goto('/dashboard-assets/run/run-demo')
  await page.getByRole('button', { name: /执行技术记录/ }).click()
  const step = page.locator('.step-header').filter({ hasText: '求解' })
  await expect(step).toHaveAttribute('aria-expanded', 'true')
  await step.click()
  await expect(step).toHaveAttribute('aria-expanded', 'false')
})
