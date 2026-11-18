import assert from 'node:assert/strict'
import test from 'node:test'
import { routesSchema } from '../src/api/routes.schemas.ts'

test('route projection preserves lineage and decisions while dropping private fields', () => {
  const value = routesSchema.parse({ policy_version: 'serial-aprs-v1', active_route_id: 'r2',
    items: [{ route_id: 'r2', parent_route_id: 'r1', kind: 'alternate', status: 'active',
      frontier_digest: 'digest', frontier: 'PRIVATE_PROOF', needs_reevaluation: true }],
    decisions: [{ selected_route_id: 'r2', pareto_route_ids: ['r2'], reason: 'route_selected',
      replayable: false, prompt: 'PRIVATE_PROMPT' }] })
  assert.equal(value.items[0]?.parent_route_id, 'r1')
  assert.equal(value.decisions[0]?.replayable, false)
  assert.doesNotMatch(JSON.stringify(value), /PRIVATE/)
  assert.equal(routesSchema.safeParse({ ...value, items: [{ ...value.items[0], status: 'verified' }] }).success, false)
})
