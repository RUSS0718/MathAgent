import { z } from 'zod'

export const presentationModeSchema = z.enum(['solve', 'teach', 'report'])

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
  sources: z.array(z.record(z.string(), z.unknown())),
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
