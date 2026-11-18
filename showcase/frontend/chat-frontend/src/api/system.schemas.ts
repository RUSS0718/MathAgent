import { z } from 'zod'

const runSummarySchema = z.object({
  run_id: z.string(), status: z.string(), created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(), solver_mode: z.string().nullable(),
  execution_mode: z.string().nullable(),
  presentation_mode: z.string().nullable(),
})

const paragraphSchema = z.object({
  id: z.string(), version: z.number().int(), text: z.string(), kind: z.string(),
  claim_refs: z.array(z.string()), status: z.string(), grade: z.string(), binding: z.string(),
})

const presentationSchema = z.object({
  schema_version: z.string().nullable(), policy_version: z.string().nullable(),
  job_id: z.string().nullable(), mode: z.string().nullable(), status: z.string().nullable(),
  answer: z.string().nullable(), answer_artifact: z.record(z.string(), z.unknown()).nullable(),
  source_fingerprint: z.string().nullable(), source_versions: z.record(z.string(), z.unknown()).nullable(),
  output_request: z.object({ id: z.string(), kind: z.string().optional(), model_calls: z.number().optional(), solver_resumed: z.boolean().optional() }).nullable(),
  artifact: z.object({ schema: z.string().optional(), sha256: z.string().optional(), id: z.string() }).nullable(),
  freshness: z.enum(['current', 'needs_review', 'unavailable']), grade_labels: z.array(z.string()),
  paragraphs: z.array(paragraphSchema),
  sources: z.array(z.object({ id: z.string(), kind: z.string().optional(), scope: z.string().optional(),
    grade: z.string().optional(), status: z.string().optional(), graph_version: z.number().optional(),
    specification_version: z.number().optional(), node_id: z.string().optional(), attempt_id: z.string().optional(),
    target_hash: z.string().optional(), proof_hash: z.string().optional(), conclusion: z.string().optional(),
    dependencies: z.array(z.string()).optional() })),
  delivery: z.object({ grade: z.string().nullable().optional(), selection: z.record(z.string(), z.unknown()).nullable(),
    unresolved_goals: z.array(z.record(z.string(), z.unknown())),
    verified_claims: z.array(z.object({ id: z.string(), text: z.string(), claim_refs: z.array(z.string()),
      status: z.string(), grade: z.string() })) }).nullable(),
})

const graphSchema = z.object({
  graph_version: z.number().int().nonnegative(),
  data_origin: z.literal('synthetic_f7_performance').optional(),
  propositions: z.array(z.object({ id: z.string(), status: z.string(), grade: z.string().nullable(),
    conflict: z.boolean(), dependencies: z.array(z.string()), sources: z.array(z.string()) })),
  attempts: z.array(z.object({ id: z.string(), status: z.string(), direction: z.string(),
    grade: z.string().nullable(), conclusion: z.string(), dependencies: z.array(z.string()), sources: z.array(z.string()) })),
})

export const systemRunsResponseSchema = z.object({
  items: z.array(runSummarySchema), total: z.number().int().nonnegative(), next_offset: z.number().int().nullable(),
})

export const systemRunResponseSchema = z.object({
  scheme: z.literal('f7-deeplink-v1'),
  run: runSummarySchema,
  presentations: z.array(z.object({ mode: z.enum(['solve', 'teach', 'report']), output_id: z.string(), artifact_id: z.string() })),
  graph: graphSchema.nullable(),
  graph_target: z.object({ status: z.string(), version: z.number().int().nullable(), node_id: z.string().nullable() }),
  selection: z.object({ status: z.string(), mode: z.string(), presentation: presentationSchema.nullable(),
    paragraph_status: z.string(), paragraph: paragraphSchema.nullable() }),
})

export type SystemRunSummary = z.infer<typeof runSummarySchema>
export type SystemRunResponse = z.infer<typeof systemRunResponseSchema>
