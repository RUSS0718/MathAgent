import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mockWorkspace } from './fixtures'

const screens = [
  ['workspace', '/dashboard-assets/session/session-demo', false],
  ['conversation', '/dashboard-assets/session/session-demo', true],
  ['settings', '/dashboard-assets/settings', false],
  ['campaigns', '/dashboard-assets/campaigns', false],
  ['campaign-detail', '/dashboard-assets/campaigns?campaign=campaign-demo', false],
  ['run', '/dashboard-assets/run/run-demo', true],
] as const

for (const width of [320, 768, 1024, 1440]) {
  for (const [name, path, populated] of screens) {
    test(`${name} at ${width}`, async ({ page }) => {
      const errors: string[] = []
      page.on('pageerror', error => errors.push(error.message))
      page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
      await page.setViewportSize({ width, height: 1000 })
      await mockWorkspace(page, populated)
      await page.goto(path)
      await expect(page.locator('.startup-state')).toHaveCount(0)
      await expect(page.locator('[aria-busy="true"]')).toHaveCount(0)
      if (populated) await expect(page.getByRole('heading', { name: '数学报告' })).toBeVisible()
      await page.evaluate(() => document.fonts.ready)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
      const accessibility = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()
      expect(accessibility.violations).toEqual([])
      await expect(page).toHaveScreenshot(`${name}-${width}.png`, { fullPage: true, animations: 'disabled', maxDiffPixels: 0 })
      expect(errors).toEqual([])
    })
  }
}

for (const kind of ['demo', 'showcase', 'unbuilt']) {
  for (const width of [320, 1440]) {
    test(`legacy ${kind} at ${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1000 })
      await page.goto(`http://127.0.0.1:5177/${kind}`)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
      expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([])
      await expect(page).toHaveScreenshot(`${kind}-${width}.png`, { fullPage: true, maxDiffPixels: 0 })
    })
  }
}
