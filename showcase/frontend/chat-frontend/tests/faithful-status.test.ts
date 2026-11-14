import assert from 'node:assert/strict'
import test from 'node:test'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createServer } from 'vite'

test('Faithful public task status distinguishes phases and uses only backend action admission', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const { default: Status } = await server.ssrLoadModule('/src/components/FaithfulTaskStatus.vue')
    for (const [phase, label] of Object.entries({ clarification: '需要澄清', converging: '正在收敛', pause_requested: '已请求暂停', paused: '已暂停', unknown: '结果未知', failed: '执行失败', budget_exhausted: '预算耗尽，任务未完成', incomplete: '任务未完成', completed: '任务完成' })) {
      const html = await renderToString(createSSRApp(Status, { state: { phase, allowed_actions: [] } }))
      assert.ok(html.includes(label), `${phase}: ${html}`)
      assert.doesNotMatch(html, /请求安全暂停|恢复执行|取消任务/)
    }
    const html = await renderToString(createSSRApp(Status, { state: { phase: 'waiting_input', allowed_actions: ['resume', 'cancel'] } }))
    assert.match(html, /恢复执行/)
    assert.match(html, /取消任务/)
    assert.doesNotMatch(html, /请求安全暂停/)
  } finally { await server.close() }
})
