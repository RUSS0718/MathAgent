import { z } from 'zod'

export const presentationModeSchema = z.enum(['solve', 'teach', 'report'])

const presentationSourceSchema = z.object({
  id: z.string(),
  scope: z.string(),
  grade: z.string(),
  status: z.string(),
  kind: z.string().optional(),
  graph_version: z.number().int().optional(),
  specification_version: z.number().int().optional(),
  node_id: z.string().optional(),
  attempt_id: z.string().optional(),
  target_hash: z.string().nullable().optional(),
  proof_hash: z.string().nullable().optional(),
  conclusion: z.string().optional(),
  dependencies: z.array(z.string()).optional(),
}).passthrough()

const presentationParagraphSchema = z.object({
  id: z.string(),
  version: z.number().int(),
  text: z.string(),
  kind: z.enum(['editorial', 'mathematical']),
  claim_refs: z.array(z.string()),
  status: z.string(),
  grade: z.string(),
  binding: z.string(),
}).passthrough()

export const presentationArtifactSchema = z.object({
  schema_version: z.string(),
  policy_version: z.string(),
  job_id: z.string(),
  mode: presentationModeSchema,
  status: z.string(),
  answer: z.string(),
  answer_artifact: z.record(z.string(), z.unknown()),
  source_fingerprint: z.string(),
  source_versions: z.record(z.string(), z.unknown()),
  sources: z.array(presentationSourceSchema),
  paragraphs: z.array(presentationParagraphSchema),
  budget: z.record(z.string(), z.unknown()).nullable(),
  request_attempts: z.array(z.record(z.string(), z.unknown())),
  scope: z.object({
    covered: z.number().int().nonnegative(),
    total: z.number().int().nonnegative(),
    unresolved: z.array(z.record(z.string(), z.unknown())),
  }),
  completion: z.string(),
  formal_verification: z.string(),
  revalidation_reason: z.string().nullable(),
  renderer: z.string(),
  output_request: z.object({
    id: z.string(), kind: z.literal('presentation_only'), model_calls: z.literal(0), solver_resumed: z.literal(false),
  }).optional(),
  delivery: z.object({
    source_fingerprint: z.string(), source_versions: z.record(z.string(), z.unknown()),
    verified_claims: z.array(presentationParagraphSchema),
    unresolved_goals: z.array(z.record(z.string(), z.unknown())),
    selection: z.object({ status: z.string() }).passthrough().nullable(),
    grade: z.string(), budget: z.record(z.string(), z.unknown()).nullable(),
    request_attempts: z.array(z.record(z.string(), z.unknown())),
  }).optional(),
  artifact: z.object({ schema: z.string(), sha256: z.string(), id: z.string() }),
}).passthrough()

export const presentationResponseSchema = z.object({
  version: z.string(),
  evidence_id: z.string(),
  status: z.string(),
  mode: presentationModeSchema,
  answer: z.string(),
  presentation: presentationArtifactSchema,
  presentation_history: z.array(presentationArtifactSchema),
  report: z.record(z.string(), z.unknown()),
})

export type PresentationMode = z.infer<typeof presentationModeSchema>
export type PresentationResponse = z.infer<typeof presentationResponseSchema>
