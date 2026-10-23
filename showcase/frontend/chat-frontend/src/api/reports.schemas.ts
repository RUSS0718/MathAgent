import { z } from 'zod'

export const reportSchema = z.object({
  version: z.string(),
  evidence_id: z.string(),
  status: z.string(),
  mode: z.enum(['live', 'fake', 'replay', 'experimental', 'unavailable', 'planned', 'star_limited']),
  solver: z.object({ solver_mode: z.string().nullable(), evidence_kind: z.string().nullable(), missing_capabilities: z.array(z.string()).nullable(), solver: z.object({ run_id: z.string(), state_revision: z.number(), phase: z.string(), status: z.string() }).passthrough().nullable() }).optional(),
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
