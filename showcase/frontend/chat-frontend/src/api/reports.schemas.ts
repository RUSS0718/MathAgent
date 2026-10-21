import { z } from 'zod'

export const reportSchema = z.object({
  version: z.string(),
  evidence_id: z.string(),
  status: z.string(),
  mode: z.enum(['live', 'fake', 'replay', 'experimental', 'unavailable', 'planned']),
  report: z.object({
    answer: z.string(),
    request_attempts: z.array(z.record(z.string(), z.unknown())).default([]),
    public_summary: z.string(),
    stage: z.string(),
    tool_summaries: z.array(z.record(z.string(), z.unknown())),
    checks: z.object({ status: z.string().optional(), findings: z.array(z.string()).optional() }).passthrough(),
    limitations: z.array(z.string()),
  }),
})

export type JobReport = z.infer<typeof reportSchema>
