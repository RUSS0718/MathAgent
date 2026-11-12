import { z } from 'zod'

/** Optional extension on solver_progress; legacy events remain valid. */
export const collaborationSchema = z.object({
  version: z.literal('workbench-v1'),
  thread_id: z.string().min(1), message_id: z.string().min(1),
  from_role: z.string().min(1), to_role: z.string().min(1),
  kind: z.enum(['challenge', 'reply', 'escalation', 'decision', 'rollback']),
  summary: z.string().max(500), content_status: z.literal('not_published'),
  thread_status: z.enum(['open', 'decided']),
  step_label: z.string().optional(), plan_version: z.number().int().nonnegative(),
  attempt_index: z.number().int().nonnegative(),
  chosen: z.enum(['CONTINUE', 'TRACE_BACK', 'APPROVE_REPLAN', 'ABORT']).optional(),
  previous_attempt_index: z.number().int().nonnegative().optional(),
  next_attempt_index: z.number().int().nonnegative().optional(),
  next_state_revision: z.number().int().nonnegative().optional(),
  changes: z.array(z.object({ op: z.enum(['del', 'keep']), step_label: z.string(), summary: z.string().max(500) })).optional(),
})
export type Collaboration = z.infer<typeof collaborationSchema>
export const evidenceChainSchema = z.array(z.object({
  step_label: z.string(), verdict: z.literal('ACCEPT'), valid: z.literal(true),
}))
