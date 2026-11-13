import { z } from 'zod'

export const backendJobStatusSchema = z.enum(['queued', 'running', 'waiting_input', 'succeeded', 'failed', 'canceled'])
export const jobActionResponseSchema = z.object({ success: z.boolean(), job_id: z.string().optional(), status: backendJobStatusSchema.optional(), existing: z.boolean().optional(), error: z.string().optional() }).passthrough()
export const activeJobSchema = z.object({ job_id: z.string(), session_id: z.string(), status: backendJobStatusSchema, last_event_id: z.number().int().nonnegative().nullable().optional() }).passthrough()
export const jobResponseSchema = z.object({ success: z.boolean() }).and(activeJobSchema)
export const activeJobsResponseSchema = z.object({ success: z.boolean(), jobs: z.array(activeJobSchema).optional(), error: z.string().optional() }).passthrough()
export type JobActionResponse = z.infer<typeof jobActionResponseSchema>
export type ActiveJobsResponse = z.infer<typeof activeJobsResponseSchema>
export type ActiveJobResponse = z.infer<typeof activeJobSchema>

export const clarificationStateSchema = z.object({
  allowed_actions: z.array(z.string()),
  clarification: z.object({
    request_id: z.string(), task_id: z.string(), input_version: z.number().int().positive(),
    question: z.string(), reason: z.string(), status: z.enum(['waiting', 'answered', 'expired']),
    answer: z.string().optional(),
  }),
})
export type ClarificationState = z.infer<typeof clarificationStateSchema>
