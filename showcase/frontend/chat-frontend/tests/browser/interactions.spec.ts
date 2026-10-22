import { expect, test } from '@playwright/test'
import { mockWorkspace } from './fixtures'

test('desktop observer really closes and gives space back', async ({ page }) => {
  await mockWorkspace(page)
  await page.goto('/dashboard-assets/session/session-demo')
  const main = page.locator('.workspace-shell > main')
  const before = await main.boundingBox()
  await page.getByRole('button', { name: '隐藏运行观察' }).click()
  await expect(page.getByRole('heading', { name: '运行观察' })).toBeHidden()
  expect((await main.boundingBox())!.width).toBeGreaterThan(before!.width)
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
