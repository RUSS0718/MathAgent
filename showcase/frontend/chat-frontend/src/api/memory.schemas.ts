import { z } from 'zod'

const runMemorySchema = z.object({
  run_id: z.string(),
  source: z.string().nullable(),
  state_revision: z.number().int().nonnegative(),
  phase: z.string().nullable(),
  status: z.string().nullable(),
  plan_version: z.unknown(),
  graph_version: z.unknown(),
  budget: z.unknown(),
  valid_evidence: z.unknown(),
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

export type RunMemoryResponse = z.infer<typeof runMemoryResponseSchema>
export type PopulationMemoryResponse = z.infer<typeof populationMemoryResponseSchema>
