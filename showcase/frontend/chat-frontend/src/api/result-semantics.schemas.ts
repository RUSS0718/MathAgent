import { z } from 'zod'

/** Product observations, independent of the legacy mathematical check status. */
export const resultSemanticsSchema = z.object({
  version: z.literal('star-result-semantics-v1'),
  execution: z.enum(['queued', 'running', 'waiting_input', 'completed', 'needs_review', 'failed', 'canceled']),
  transport: z.enum(['known', 'unknown', 'pending', 'unavailable']),
  whole_review: z.enum(['accepted', 'rejected', 'not_reviewed', 'invalid_source']),
  binding: z.enum(['same_artifact', 'artifact_changed', 'unbound']),
  formal_verification: z.literal('not_verified'),
  verification_requirement: z.enum(['default', 'required_unmet']).default('default'),
})

export type ResultSemantics = z.infer<typeof resultSemanticsSchema>
