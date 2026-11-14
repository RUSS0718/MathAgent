import test from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'

test('serial intervention exposes source, adoption and continuation without promoting evidence', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const { default: Status } = await server.ssrLoadModule('/src/components/SerialInterventionStatus.vue')
    const value = { status: 'completed', reason: null, pair_id: 'pair-1', continuation: 'main_task_continues',
      decision: { reason: '改用归纳法核对边界', hypothesis: '原方法未覆盖边界', method_id: 'induction' },
      adoptions: [{ status: 'adopted', reason: 'applicable_reviewed_result', evidence_grade: 'LLM_REVIEWED',
        reference: { pair_id: 'pair-1', arm: 'intervention', source_version: 'abc123', scope: '步骤 2',
          premises: ['PRIVATE_PREMISE'], report: 'PRIVATE_PROOF' } }],
    }
    const html = await renderToString(createSSRApp(Status, { value }))
    for (const text of ['串行自主干预', '改用归纳法核对边界', '已采用', 'pair-1', 'abc123', '步骤 2', 'LLM_REVIEWED', '主任务继续', '整题审查']) assert.ok(html.includes(text), text)
    assert.doesNotMatch(html, /PRIVATE_|机器证明通过|整题已完成/)
    const unknown = await renderToString(createSSRApp(Status, { value: { ...value, status: 'needs_review', continuation: 'pending' } }))
    assert.match(unknown, /等待复核/)
    assert.doesNotMatch(unknown, /主任务继续/)
    const revoked = await renderToString(createSSRApp(Status, { value: {
      ...value, status: 'needs_review', reason: 'population_intervention_permission_revoked', continuation: 'pending', origin: 'population',
    } }))
    assert.match(revoked, /干预权限已撤销/)
    assert.doesNotMatch(revoked, /未知结果保留原预留/)
    const population = await renderToString(createSSRApp(Status, { value: {
      ...value, origin: 'population', route_id: 'route-1', source_version: 'source-177',
    } }))
    for (const text of ['并发收敛后干预', 'route-1', 'source-177']) assert.ok(population.includes(text), text)
    assert.doesNotMatch(population, /串行自主干预|PRIVATE_/)
    const invalid = await renderToString(createSSRApp(Status, { value: { status: 'invented' } }))
    assert.doesNotMatch(invalid, /串行自主干预/)
  } finally { await server.close() }
})
