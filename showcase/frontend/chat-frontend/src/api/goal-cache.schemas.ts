import { z } from 'zod'

const goalCacheEntrySchema = z.object({
  cache_id: z.string(),
  state: z.enum(['active', 'stale', 'invalidated']),
  reason: z.string().optional(),
  created_at: z.string(),
  updated_at: z.string(),
  source_run_id: z.string().optional(),
  source_attempt_id: z.string().optional(),
  source_grade: z.string().optional(),
  grade_ceiling: z.string().optional(),
}).passthrough()

const goalCacheEventSchema = z.object({
  cache_id: z.string().optional(),
  event: z.string(),
  created_at: z.string(),
  details: z.record(z.string(), z.unknown()).optional(),
}).passthrough()

export const goalCacheResponseSchema = z.object({
  success: z.literal(true),
  authority: z.literal('metadata_only'),
  enabled: z.boolean(),
  entries: z.array(goalCacheEntrySchema),
  events: z.array(goalCacheEventSchema),
}).passthrough()

export type GoalCacheResponse = z.infer<typeof goalCacheResponseSchema>
