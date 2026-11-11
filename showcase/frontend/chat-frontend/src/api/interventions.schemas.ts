import { z } from 'zod'

const failureSourceSchema = z.object({
  source_event_id: z.string(),
  source_state_revision: z.number().int().nonnegative(),
  event_type: z.literal('step_reviewed'),
  verdict: z.enum(['CHALLENGE', 'TRACE_BACK', 'PROPOSE_REPLAN']),
  step_label: z.string(),
})

const rootObligationSchema = z.object({ obligation_id: z.string(), proposition: z.string() })
const interventionViewSchema = z.object({
  job_id: z.string(),
  status: z.string(),
  checkpoint_revision: z.number().int().nonnegative().nullable(),
  failure_sources: z.array(failureSourceSchema),
  root_obligations: z.array(rootObligationSchema),
  current_method_id: z.string().nullable(),
  hypotheses: z.array(z.record(z.string(), z.unknown())),
  actions: z.array(z.record(z.string(), z.unknown())),
  pairs: z.array(z.record(z.string(), z.unknown())),
  effects: z.unknown(),
}).passthrough()

export const interventionsResponseSchema = z.object({
  success: z.literal(true),
  interventions: interventionViewSchema,
}).passthrough()

export const interventionMutationSchema = z.object({
  success: z.literal(true),
  job_id: z.string().optional(),
  status: z.string().optional(),
  hypothesis_id: z.string().optional(),
  action_id: z.string().optional(),
  pair_id: z.string().optional(),
  source_event_id: z.string().optional(),
  source_state_revision: z.number().int().nonnegative().optional(),
  budget_reservation: z.unknown().optional(),
}).passthrough()

export type InterventionFailureSource = z.infer<typeof failureSourceSchema>
export type InterventionRootObligation = z.infer<typeof rootObligationSchema>
export type InterventionsView = z.infer<typeof interventionViewSchema>

export type InterventionFailureCategory =
  | 'method_mismatch'
  | 'lemma_structure'
  | 'decomposition_granularity'
  | 'inefficient_order'
  | 'underused_premise'

export type InterventionMethod = 'direct' | 'contradiction' | 'induction' | 'construction' | 'computation'

export interface CreateInterventionHypothesisInput {
  hypothesis_id: string
  failure_category: InterventionFailureCategory
  source_event_id: string
  source_state_revision: number
  affected_roots: InterventionRootObligation[]
  failure_symptom: string
  diagnostic_evidence: { event_type: 'step_reviewed'; verdict: InterventionFailureSource['verdict'] }
  candidate_action_ids: [string, string]
  falsification_criteria: { condition: string }
  priority: number
}

export interface CreateInterventionActionInput {
  action_id: string
  action_type: 'reasoning_method'
  target: 'current_step'
  parameters: { method_id: InterventionMethod }
}

export interface ReserveInterventionPairInput {
  pair_id: string
  hypothesis_id: string
  control_action_id: string
  intervention_action_id: string
  seed: number
}
