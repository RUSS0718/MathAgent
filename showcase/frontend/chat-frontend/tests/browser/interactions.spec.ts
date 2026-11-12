import { expect, test } from '@playwright/test'
import { mockWorkspace } from './fixtures'

test('new workspace replaces the observer and shares state across its views', async ({ page }) => {
  await mockWorkspace(page, true)
  await page.goto('/dashboard-assets/session/session-demo')
  await expect(page.locator('[data-workspace="conversation-workbench"]')).toBeVisible()
  await expect(page.locator('.workspace-shell')).toHaveCount(0)
  const workbench = page.getByRole('region', { name: '对话式执行工作台' })
  await expect(workbench.locator('[data-workbench-event]')).toHaveCount(2)
  await workbench.getByRole('button', { name: '完整星图', exact: true }).click()
  await expect(workbench.locator('.constellation:not(.mini)')).toBeVisible()
  await workbench.getByRole('button', { name: '对话事件', exact: true }).click()
  await expect(workbench.locator('[data-workbench-event]:visible')).toHaveCount(2)
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
  await page.goto('/dashboard-assets/run/run-demo')
  const step = page.locator('.step-header').filter({ hasText: '求解' })
  await expect(step).toHaveAttribute('aria-expanded', 'true')
  await step.click()
  await expect(step).toHaveAttribute('aria-expanded', 'false')
})
