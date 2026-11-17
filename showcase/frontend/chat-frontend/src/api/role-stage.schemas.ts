import { z } from 'zod'

export const roleStageSchema = z.object({
  version: z.literal('role-stage-v1'), job_id: z.string(), role: z.string(), status: z.string(),
  content_status: z.enum(['published', 'unavailable']),
  results: z.array(z.object({
    source_ref: z.string(), plan_version: z.number(), attempt_index: z.number(), stage: z.string(),
    body_version: z.string(), validity: z.enum(['current', 'replaced']),
    check: z.object({ scope: z.literal('plan_structure'), body_version: z.string() }),
    items: z.array(z.object({ label: z.string(), title: z.string(), objective: z.string(), depends_on: z.array(z.string()) })),
  })),
})
export type RoleStage = z.infer<typeof roleStageSchema>
