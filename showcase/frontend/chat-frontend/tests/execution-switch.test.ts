import test from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'

test('route switching renders durable convergence, review and completion distinctly', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const { default: Status } = await server.ssrLoadModule('/src/components/AutonomousRouteStatus.vue')
    for (const [status, label] of [['converging', '切换中'], ['needs_review', '待复核'],
      ['switched', '已切换'], ['canceled', '切换已取消'], ['rejected', '切换未准入']]) {
      const html = await renderToString(createSSRApp(Status, {
        executionSwitch: { status, source: 'population', target: 'serial',
          reason: '独立方向已收敛', checkpoint_revision: status === 'switched' ? 17 : null },
      }))
      assert.match(html, new RegExp(label!))
      assert.match(html, /并发 → 串行/)
      assert.match(html, /独立方向已收敛/)
      if (status === 'switched') assert.match(html, /检查点版本 17/)
      assert.doesNotMatch(html, /自动重试|重新提交/)
    }
    const invalid = await renderToString(createSSRApp(Status, {
      executionSwitch: { status: 'made_up', source: 'serial', target: 'population' },
    }))
    assert.doesNotMatch(invalid, /运行路线切换/)
  } finally { await server.close() }
})
