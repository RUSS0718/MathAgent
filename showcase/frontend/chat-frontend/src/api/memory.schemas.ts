import { z } from 'zod'

const runEvidenceSchema = z.object({
  result_id: z.string().optional(),
  category: z.string().optional(),
  evidence_level: z.string().optional(),
  source: z.unknown().optional(),
  obligation_id: z.string().optional(),
}).passthrough()

const runMemorySchema = z.object({
  run_id: z.string(),
  source: z.string().nullable(),
  state_revision: z.number().int().nonnegative(),
  phase: z.string().nullable(),
  status: z.string().nullable(),
  plan_version: z.unknown(),
  graph_version: z.unknown(),
  budget: z.unknown(),
  valid_evidence: z.array(runEvidenceSchema),
  invalidated_count: z.number().int().nonnegative(),
}).passthrough()

export const runMemoryResponseSchema = z.object({
  success: z.literal(true),
  run_memory: runMemorySchema,
}).passthrough()

const routeObservationSchema = z.object({
  source_run_id: z.string(),
  source_state_revision: z.number().int().nonnegative(),
  route_id: z.string(),
  parent_route_id: z.string().nullable(),
  status: z.string(),
  stop_reason: z.string().nullable(),
  graph_version: z.unknown(),
  plan_version: z.unknown(),
  policy_version: z.unknown(),
  unknown_observation_count: z.number().int().nonnegative().nullable(),
}).passthrough()

export const populationMemoryResponseSchema = z.object({
  success: z.literal(true),
  authority: z.literal('observations_only'),
  observations: z.array(routeObservationSchema),
  total_jobs: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
  offset: z.number().int().nonnegative(),
}).passthrough()

export const populationMemoryControlResponseSchema = z.object({
  success: z.literal(true),
  authority: z.literal('observations_only'),
  injection_enabled: z.boolean(),
  observations: z.array(z.object({
    record_id: z.string(),
    observation: z.object({
      outcome: z.unknown(),
      applicability: z.unknown(),
      versions: z.unknown(),
      cost: z.unknown(),
      content: z.unknown(),
    }).passthrough().refine(
      value => ['outcome', 'applicability', 'versions', 'cost', 'content'].every(field => Object.prototype.hasOwnProperty.call(value, field)),
      { error: 'Missing population observation field' },
    ),
    provenance: z.unknown(),
    authority: z.literal('historical_observation'),
    trust: z.literal('advisory'),
  }).passthrough().refine(
    value => Object.prototype.hasOwnProperty.call(value, 'provenance'),
    { error: 'Missing population observation provenance' },
  )),
}).passthrough()

export const populationMemoryUpdateResponseSchema = z.object({
  success: z.literal(true),
  enabled: z.boolean(),
  injection_enabled: z.boolean(),
}).passthrough()

export type RunMemoryResponse = z.infer<typeof runMemoryResponseSchema>
export type PopulationMemoryResponse = z.infer<typeof populationMemoryResponseSchema>
export type PopulationMemoryControlResponse = z.infer<typeof populationMemoryControlResponseSchema>
