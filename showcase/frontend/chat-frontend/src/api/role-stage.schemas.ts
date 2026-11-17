import { z } from 'zod'

const validity = z.enum(['current', 'historical', 'replaced', 'invalidated'])
const sourceMetadata = z.object({
  source_ref: z.string(), plan_version: z.number(), attempt_index: z.number(), stage: z.string(),
  body_version: z.string(), validity,
})
export const roleStageSchema = z.object({
  version: z.literal('role-stage-v1'), job_id: z.string(), role: z.string(), status: z.string(),
  content_status: z.enum(['published', 'unavailable', 'empty', 'not_published']),
  history: z.array(sourceMetadata).default([]),
  results: z.array(sourceMetadata.extend({
    check: z.object({ scope: z.string(), body_version: z.string(), status: z.string().optional(), label: z.string().optional() }),
    items: z.array(z.object({ label: z.string(), title: z.string(), objective: z.string(), depends_on: z.array(z.string()) })).default([]),
    sections: z.array(z.object({ label: z.string(), text: z.string() })).default([]),
    summary: z.string().optional(),
  })),
})
export type RoleStage = z.infer<typeof roleStageSchema>
