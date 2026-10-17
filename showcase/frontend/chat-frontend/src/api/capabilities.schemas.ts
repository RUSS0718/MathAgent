import { z } from 'zod'

const capabilitySchema = z.object({
  enabled: z.boolean(),
  status: z.enum(['available', 'unavailable', 'experimental']).optional(),
  reason: z.string().nullable().optional(),
  mime: z.string().optional(),
  max_bytes: z.number().optional(),
})

export const capabilitiesResponseSchema = z.object({
  profile: z.string(),
  execution: z.object({ mode: z.string(), provider: z.string(), status: z.string() }).optional(),
  jobs: z.object({ enabled: z.boolean(), status: z.string() }),
  sse: z.object({ enabled: z.boolean(), status: z.string() }),
  verification_mode: z.array(z.string()),
  files: z.object({ upload: capabilitySchema }),
  capabilities: z.object({ jobs: z.boolean(), sse: z.boolean(), verification_mode: z.array(z.string()), file_upload: capabilitySchema }),
})
export type CapabilitiesResponse = z.infer<typeof capabilitiesResponseSchema>
