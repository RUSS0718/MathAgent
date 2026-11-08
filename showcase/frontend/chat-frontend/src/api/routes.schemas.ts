import { z } from 'zod'

// Public persisted route summaries; arbitrary frontier/proof fields are stripped.
export const routesSchema = z.object({
  policy_version: z.string(),
  active_route_id: z.string().nullable(),
  items: z.array(z.object({
    route_id: z.string(), parent_route_id: z.string().nullable().optional(),
    kind: z.enum(['primary', 'alternate']),
    status: z.enum(['created', 'eligible', 'active', 'stalled', 'completed', 'terminated', 'pruned']),
    frontier_digest: z.string(), graph_version: z.number().int().nullable().optional(),
    policy_version: z.string().optional(), stop_reason: z.string().nullable().optional(),
    elimination_reason: z.string().nullable().optional(), needs_reevaluation: z.boolean().optional(),
  })),
  decisions: z.array(z.object({
    state_revision: z.number().int().optional(), selected_route_id: z.string().nullable().optional(),
    pareto_route_ids: z.array(z.string()).optional(), reason: z.string().optional(),
    policy_version: z.string().optional(), replayable: z.boolean().optional(),
  })),
})
export type RouteSummary = z.infer<typeof routesSchema>
