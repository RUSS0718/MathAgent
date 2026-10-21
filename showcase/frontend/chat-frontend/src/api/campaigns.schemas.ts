import { z } from 'zod'
const mode = z.enum(['live', 'fake', 'replay', 'experimental', 'unavailable', 'planned'])
const arm = z.object({ status: z.string(), job_id: z.string().nullable(), error: z.string().nullable().optional(), quality: z.object({ status: z.string() }).passthrough(), usage: z.object({ http_attempts: z.number().nullable(), unknown_attempts: z.number().nullable() }).passthrough(), latency_seconds: z.number().nullable().optional(), cost: z.number().nullable(), requested_model: z.string().optional(), returned_models: z.array(z.string()).optional(), strategy_status: z.string().optional() }).passthrough()
export const campaignSummarySchema = z.object({ campaign_id: z.string(), mode, status: z.string(), common_hash: z.string(), summary: z.object({ total_pairs: z.number(), completed_pairs: z.number(), successful_pairs: z.number() }).passthrough().optional() })
export const campaignSchema = campaignSummarySchema.extend({ pairs: z.array(z.object({ pair_id: z.string(), problem_hash: z.string(), arms: z.object({ baseline: arm, candidate: arm }) }).passthrough()), archive: z.object({ path: z.string(), sha256: z.string() }).optional(), config_hash: z.string().optional() }).passthrough()
export const campaignsSchema = z.object({ campaigns: z.array(campaignSummarySchema), offset: z.number(), limit: z.number() })
export type Campaign = z.infer<typeof campaignSchema>

