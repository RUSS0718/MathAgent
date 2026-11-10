import { expect, test } from '@playwright/test'
import { mockWorkspace } from './fixtures'

test('opt-in memory review shows the persisted evidence level and advisory history', async ({ page }) => {
  await mockWorkspace(page)
  await page.route('**/api/agent/jobs/run-demo/memory', route => route.fulfill({ json: {
    success: true,
    run_memory: {
      run_id: 'run-demo', source: 'authoritative_run_snapshot', state_revision: 4,
      phase: 'TERMINAL', status: 'completed', plan_version: 2, graph_version: 3,
      budget: { http_attempts: 1 }, invalidated_count: 0,
      valid_evidence: [{ result_id: 'evidence-1', evidence_level: 'llm_reviewed', category: 'Lemma' }],
    },
  } }))
  await page.route('**/api/sessions/session-demo/population-memory', route => route.fulfill({ json: {
    success: true, authority: 'observations_only', total_jobs: 1, limit: 25, offset: 0,
    observations: [{ source_run_id: 'run-older', source_state_revision: 2,
      route_id: 'route-1', parent_route_id: null, status: 'stopped', stop_reason: null,
      graph_version: 1, plan_version: 1, policy_version: 1, unknown_observation_count: 1 }],
  } }))

  await page.goto('/dashboard-assets/run/run-demo')
  const memory = page.getByRole('region', { name: '运行记忆与历史路线观察' })
  await expect(memory).toBeVisible()
  await expect(memory).toContainText('authoritative_run_snapshot')
  await expect(memory).toContainText('evidence-1 · 等级：llm_reviewed · 类别：Lemma')
  await expect(memory).toContainText('run-older')
  await expect(memory).toContainText('未知观察数')
  await expect(memory).toContainText('不构成数学证明')
})

test('default-off memory routes leave the review panel hidden', async ({ page }) => {
  await mockWorkspace(page)
  await page.goto('/dashboard-assets/run/run-demo')
  await expect(page.getByRole('region', { name: '运行记忆与历史路线观察' })).toHaveCount(0)
})
