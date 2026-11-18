import { z } from 'zod'
import { resultSemanticsSchema } from './result-semantics.schemas.ts'
import { routesSchema } from './routes.schemas.ts'

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
    grade: z.enum(['llm_reviewed', 'tool_verified', 'mixed']).nullable(), conflict: z.boolean(),
    dependencies: z.array(z.string()), sources: z.array(z.string()),
  })),
  attempts: z.array(z.object({
    id: z.string(), status: z.enum(['proposed', 'accepted', 'rejected', 'invalidated', 'unknown']),
    direction: z.enum(['support', 'counterexample']), grade: z.enum(['llm_reviewed', 'tool_verified', 'mixed']).nullable(),
    conclusion: z.string(), dependencies: z.array(z.string()), sources: z.array(z.string()),
  })),
})
export type ProofGraph = z.infer<typeof proofGraphSchema>

export const progressSchema = z.object({
  routes: routesSchema.optional(),
  proof_graph: proofGraphSchema.optional(),
  root_obligations: rootObligationsSchema.optional(),
  plan_history: planHistorySchema.optional(),
  steps: z.array(z.record(z.string(), z.unknown())).optional(),
}).passthrough()

export const populationProjectionSchema = z.object({
  version: z.string(),
  routes: z.array(z.object({
    ordinal: z.number().int().positive(), parent_ordinal: z.number().int().positive().nullable(),
    status: z.string(), step_count: z.number().int().nonnegative(),
    completed_steps: z.number().int().nonnegative(), result: z.string(),
  })).optional(),
  scheduler: z.object({
    round: z.number().int().nonnegative(),
    member_count: z.number().int().nonnegative(),
    opportunities_used: z.number().int().nonnegative(),
    verified_gain_count: z.number().int().nonnegative(),
    route_counts: z.record(z.string(), z.number().int().nonnegative()),
    paused: z.boolean(),
  }),
  resources: z.object({
    worker_slots_in_use: z.number().int().nonnegative(),
    http_inflight: z.number().int().nonnegative(),
    unknown_routes: z.number().int().nonnegative(),
    unknown_requests: z.number().int().nonnegative(),
  }),
  delivery: z.object({ status: z.string().optional(), reason: z.string().optional() }),
  settlement: z.object({
    status: z.string().optional(), unknown_count: z.number().int().nonnegative().optional(),
  }),
})

const nullableStringSchema = z.string().nullable()

export const formalAttemptSchema = z.object({
  schema_version: z.number().int().optional(),
  status: z.enum(['disabled', 'dispatched', 'unsupported', 'unavailable', 'not_verified', 'partial', 'timeout', 'error', 'failed', 'unknown', 'solved']),
  grade: z.enum(['L2', 'L3']).nullable(),
  attempt_id: z.string(),
  parent_attempt_id: nullableStringSchema,
  reason: nullableStringSchema,
  proof_artifact: z.record(z.string(), z.unknown()).nullable(),
  specifications: z.record(z.string(), z.unknown()),
  cost: z.record(z.string(), z.unknown()),
  lineage: z.record(z.string(), z.unknown()),
}).passthrough()

export const formalVerificationSchema = z.object({
  schema_version: z.literal('formal-verification-v1'),
  assessment: z.object({
    status: z.enum(['default', 'met', 'unmet']),
    reason: z.string(),
    scope: z.enum(['original_problem', 'formal_target']),
    required_grade: z.enum(['L2', 'L3']),
    covered_obligation_ids: z.array(z.string()),
  }).optional(),
  policy: z.record(z.string(), z.unknown()),
  policy_hash: z.string(),
  status: z.enum(['disabled', 'dispatched', 'unsupported', 'unavailable', 'not_verified', 'partial', 'timeout', 'error', 'failed', 'unknown', 'solved']),
  grade: z.enum(['L2', 'L3']).nullable(),
  current_attempt_id: nullableStringSchema,
  current: formalAttemptSchema.nullable(),
  attempts: z.array(formalAttemptSchema),
  lineage: z.record(z.string(), z.unknown()),
}).passthrough()
export type FormalVerification = z.infer<typeof formalVerificationSchema>
export type FormalAttempt = z.infer<typeof formalAttemptSchema>
export const proverRouteSchema = z.object({
  backend_id: z.string(),
  target_type: z.string(),
  selection_reason: z.string().optional(),
  environment_identity: z.record(z.string(), z.unknown()).optional(),
  input_format: z.string().optional(),
  output_format: z.string().optional(),
  deterministic: z.boolean().optional(),
  unavailable_reason: nullableStringSchema.optional(),
  attempt_id: z.string(),
  parent_attempt_id: nullableStringSchema,
  status: z.string(),
  grade: z.enum(['L1', 'L2', 'L3', 'LLM_REVIEWED']).nullable(),
  maximum_grade: z.enum(['L1', 'L2', 'L3', 'LLM_REVIEWED']),
  cost: z.record(z.string(), z.unknown()),
  lineage: z.record(z.string(), z.unknown()),
}).passthrough()
export type ProverRoute = z.infer<typeof proverRouteSchema>
export const reportSchema = z.object({
  version: z.string(),
  evidence_id: z.string(),
  status: z.string(),
  mode: z.enum(['live', 'fake', 'replay', 'experimental', 'unavailable', 'planned', 'star_limited', 'star_limited_best_effort', 'star_reference', 'star_best_effort', 'star_population']),
  prover_routes: z.array(proverRouteSchema).optional(),
  solver: z.object({ solver_mode: z.string().nullable(), evidence_kind: z.string().nullable(), missing_capabilities: z.array(z.string()).nullable(), formal_verification: formalVerificationSchema.optional(), solver: z.object({ run_id: z.string(), state_revision: z.number(), phase: z.string(), status: z.string(), recovery: recoverySchema.optional(), progress: progressSchema.optional(), population: populationProjectionSchema.optional(), candidate_history: z.array(z.record(z.string(), z.unknown())).optional(), best_effort: z.record(z.string(), z.unknown()).nullable().optional(), formal_verification: formalVerificationSchema.optional(), prover_routes: z.array(proverRouteSchema).optional() }).passthrough().nullable() }).optional(),
  report: z.object({
    budget: z.record(z.string(), z.unknown()).nullable().optional(),
    answer: z.string(),
    request_attempts: z.array(z.record(z.string(), z.unknown())).default([]),
    public_summary: z.string(),
    stage: z.string(),
    tool_summaries: z.array(z.record(z.string(), z.unknown())),
    prover_routes: z.array(proverRouteSchema).optional(),
    checks: z.object({ status: z.string().optional(), findings: z.array(z.string()).optional(), history: z.array(z.record(z.string(), z.unknown())).optional() }).passthrough(),
    semantics: resultSemanticsSchema.nullable().optional(),
    limitations: z.array(z.string()),
  }),
})

export type JobReport = z.infer<typeof reportSchema>
