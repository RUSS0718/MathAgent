import { expect, test } from '@playwright/test'
import { mockWorkspace } from './fixtures'

test('owned memory import, consent and clear use the existing entry', async ({ page }, testInfo) => {
  await mockWorkspace(page)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  let enabled = false, imported = false, cleared = false
  let rejectClear = true
  const writes: string[] = []
  const observation = { record_id: 'source-record', observation: { outcome: 'success', applicability: {}, versions: {}, cost: {}, content: {} }, provenance: { source_run: 'owned-run' }, authority: 'historical_observation', trust: 'advisory' }
  await page.route('**/api/sessions/*/memory/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname
    if (req.method() !== 'GET') writes.push(req.method())
    if (path.endsWith('/injection')) {
      enabled = req.postDataJSON().enabled
      return route.fulfill({ json: { success: true, enabled, injection_enabled: enabled } })
    }
    if (path.endsWith('/imports')) {
      expect(req.postDataJSON()).toEqual({ source_session_id: 'owned-session', source_kind: 'population', source_scope_id: 'owned-session', record_id: 'source-record' })
      imported = true
      return route.fulfill({ status: 201, json: { success: true, record_id: 'imported-record', authority: 'advisory' } })
    }
    if (req.method() === 'DELETE') {
      if (rejectClear) { rejectClear = false; return route.fulfill({ status: 500, json: { error: '清理请求失败' } }) }
      cleared = true
      return route.fulfill({ json: { success: true, cleared: true } })
    }
    if (path.includes('/denied-session/')) return route.fulfill({ status: 403, json: { error: '同所有者会话才可读取' } })
    return route.fulfill({ json: { success: true, authority: 'observations_only', injection_enabled: enabled, observations: path.includes('/owned-session/') || (imported && !cleared) ? [observation] : [] } })
  })
  await page.goto('/dashboard-assets/run/run-demo')
  const panel = page.getByRole('region', { name: '会话记忆观察与注入设置' })
  await expect(panel).toContainText('后续模型请求')
  await expect(panel).toContainText('重启恢复')
  await expect(panel).not.toContainText('已开始的 Run 可能继续使用')
  await panel.getByRole('checkbox').check()
  await expect(panel).toContainText('服务端报告的注入状态：启用')
  await panel.getByRole('checkbox').uncheck()
  await expect(panel).toContainText('服务端报告的注入状态：停用')
  await panel.getByLabel('来源会话 ID').fill('denied-session')
  await panel.getByRole('button', { name: '读取来源观察' }).click()
  await expect(panel.getByRole('alert')).toContainText('同所有者')
  await expect(panel.getByRole('button', { name: '显式导入所选观察' })).toBeDisabled()
  await panel.getByLabel('来源会话 ID').fill('owned-session')
  await panel.getByRole('button', { name: '读取来源观察' }).click()
  await expect(panel).toContainText('owned-run')
  await panel.getByLabel('来源观察', { exact: true }).selectOption('source-record')
  await panel.getByRole('button', { name: '显式导入所选观察' }).click()
  await expect(panel).toContainText('已导入')
  await expect(panel).toContainText('来源记录')
  await panel.getByRole('button', { name: '清理此会话记忆' }).click()
  await expect(panel.getByRole('alert')).toContainText('清理请求失败')
  await expect(panel).not.toContainText('已清理')
  await expect(panel).toContainText('来源记录')
  await panel.getByRole('button', { name: '清理此会话记忆' }).click()
  await expect(panel).toContainText('已清理')
  await expect(panel).toContainText('没有可显示的记忆观察')
  expect(writes).toEqual(['PUT', 'PUT', 'POST', 'DELETE', 'DELETE'])
  await panel.getByLabel('来源会话 ID').fill('another-session')
  await expect(panel.getByRole('button', { name: '显式导入所选观察' })).toBeDisabled()
  await panel.getByLabel('来源会话 ID').focus()
  await page.keyboard.press('Tab')
  await expect(panel.getByRole('button', { name: '读取来源观察' })).toBeFocused()
  await page.setViewportSize({ width: 320, height: 844 })
  expect(await panel.evaluate(el => el.scrollWidth <= el.getBoundingClientRect().width + 1)).toBe(true)
  await panel.screenshot({ path: testInfo.outputPath('memory-320.png') })
  expect(errors).toEqual([])
})
