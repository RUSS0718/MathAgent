import { expect, test } from '@playwright/test'
test('196 real Flask ordinary solve and read-only history', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  await page.goto('/dashboard-assets/')
  await page.getByRole('textbox', { name: '数学问题' }).fill('解方程 x² − 5x + 6 = 0')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  const answer = page.getByRole('region', { name: '最终答复' })
  await expect(answer).toContainText('求解', { timeout: 12000 })
  await expect(answer.locator('.report-content')).not.toBeEmpty()
  await page.goto(page.url().replace('/dashboard/session/', '/dashboard-assets/session/'))
  await expect(answer.locator('.report-content')).not.toBeEmpty()
  await expect(page.getByRole('link', { name: '运行详情' })).toHaveCount(0)
  expect(errors).toEqual([])
})
test('196 real Flask reviewer denial and grant', async ({ page }) => {
  await page.goto('/dashboard-assets/settings')
  await expect(page.getByRole('heading', { name: '技术审阅需要授权' })).toBeVisible()
  await page.getByLabel('审阅密钥').fill('local-browser-fixture')
  await page.getByRole('button', { name: '授权审阅' }).click()
  await expect(page.getByRole('heading', { name: '技术审阅需要授权' })).toHaveCount(0)
  await expect(page.getByRole('main')).toBeVisible()
})
