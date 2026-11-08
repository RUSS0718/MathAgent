import { z } from 'zod'
import { resultSemanticsSchema } from './result-semantics.schemas.ts'

export const recoverySchema = z.object({
  status: z.enum(['safe', 'needs_review']),
  unknown_calls: z.array(z.object({ call_id: z.string(), role: z.string(), status: z.string() })),
  unknown_tools: z.array(z.object({ call_id: z.string(), status: z.string() })).optional(),
  retries: z.array(z.object({ call_id: z.string(), retry_of: z.string(), status: z.string() })),
})

export const rootObligationsSchema = z.object({
  covered: z.number().int().nonnegative(),
  total: z.number().int().nonnegative(),
  items: z.array(z.object({
    ordinal: z.number().int().positive(),
    type: z.string().nullable().optional(),
    status: z.string(),
  })),
})

export const planHistorySchema = z.array(z.object({
  plan_version: z.number().int().positive(),
  attempt_index: z.number().int().nonnegative(),
  status: z.enum(['current', 'archived', 'retried']),
  step_count: z.number().int().nonnegative().nullable(),
  outcome: z.enum(['replan', 'problem_spec_change', 'trace_back']).nullable(),
}))

export const proofGraphSchema = z.object({
  graph_version: z.number().int().nonnegative(),
  propositions: z.array(z.object({
    id: z.string(), status: z.enum(['unresolved', 'supported', 'invalidated', 'refuted']),
    grade: z.string().nullable(), conflict: z.boolean(),
    dependencies: z.array(z.string()), sources: z.array(z.string()),
  })),
  attempts: z.array(z.object({
    id: z.string(), status: z.enum(['proposed', 'accepted', 'rejected', 'invalidated', 'unknown']),
    direction: z.enum(['support', 'counterexample']), grade: z.string().nullable(),
    conclusion: z.string(), dependencies: z.array(z.string()), sources: z.array(z.string()),
  })),
})
export type ProofGraph = z.infer<typeof proofGraphSchema>

export const progressSchema = z.object({
  proof_graph: proofGraphSchema.optional(),
  root_obligations: rootObligationsSchema.optional(),
  plan_history: planHistorySchema.optional(),
  steps: z.array(z.record(z.string(), z.unknown())).optional(),
}).passthrough()

export const reportSchema = z.object({
  version: z.string(),
  evidence_id: z.string(),
  status: z.string(),
  mode: z.enum(['live', 'fake', 'replay', 'experimental', 'unavailable', 'planned', 'star_limited', 'star_limited_best_effort', 'star_reference', 'star_best_effort']),
  solver: z.object({ solver_mode: z.string().nullable(), evidence_kind: z.string().nullable(), missing_capabilities: z.array(z.string()).nullable(), solver: z.object({ run_id: z.string(), state_revision: z.number(), phase: z.string(), status: z.string(), recovery: recoverySchema.optional(), progress: progressSchema.optional(), candidate_history: z.array(z.record(z.string(), z.unknown())).optional(), best_effort: z.record(z.string(), z.unknown()).nullable().optional() }).passthrough().nullable() }).optional(),
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
