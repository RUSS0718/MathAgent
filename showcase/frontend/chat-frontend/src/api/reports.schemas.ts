import { z } from 'zod'
import { resultSemanticsSchema } from './result-semantics.schemas.ts'

export const recoverySchema = z.object({
  status: z.enum(['safe', 'needs_review']),
  unknown_calls: z.array(z.object({ call_id: z.string(), role: z.string(), status: z.string() })),
  unknown_tools: z.array(z.object({ call_id: z.string(), status: z.string() })).optional(),
  retries: z.array(z.object({ call_id: z.string(), retry_of: z.string(), status: z.string() })),
})

export const reportSchema = z.object({
  version: z.string(),
  evidence_id: z.string(),
  status: z.string(),
  mode: z.enum(['live', 'fake', 'replay', 'experimental', 'unavailable', 'planned', 'star_limited', 'star_limited_best_effort', 'star_reference', 'star_best_effort']),
  solver: z.object({ solver_mode: z.string().nullable(), evidence_kind: z.string().nullable(), missing_capabilities: z.array(z.string()).nullable(), solver: z.object({ run_id: z.string(), state_revision: z.number(), phase: z.string(), status: z.string(), recovery: recoverySchema.optional(), progress: z.record(z.string(), z.unknown()).optional(), candidate_history: z.array(z.record(z.string(), z.unknown())).optional(), best_effort: z.record(z.string(), z.unknown()).nullable().optional() }).passthrough().nullable() }).optional(),
  report: z.object({
    budget: z.record(z.string(), z.unknown()).nullable().optional(),
    answer: z.string(),
    request_attempts: z.array(z.record(z.string(), z.unknown())).default([]),
    public_summary: z.string(),
    stage: z.string(),
    tool_summaries: z.array(z.record(z.string(), z.unknown())),
    checks: z.object({ status: z.string().optional(), findings: z.array(z.string()).optional(), history: z.array(z.record(z.string(), z.unknown())).optional() }).passthrough(),
    semantics: resultSemanticsSchema.nullable().optional(),
    limitations: z.array(z.string()),
  }),
})

export type JobReport = z.infer<typeof reportSchema>
