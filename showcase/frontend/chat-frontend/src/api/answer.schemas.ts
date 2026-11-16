import { z } from 'zod'
export const finalAnswerSchema = z.object({
  job_id: z.string(), status: z.string(), mode: z.enum(['solve', 'teach', 'report']), answer: z.string().nullable(),
  presentation_status: z.enum(['pending', 'ready', 'failed', 'legacy', 'stale', 'unavailable']), notice: z.string().nullable(),
})
