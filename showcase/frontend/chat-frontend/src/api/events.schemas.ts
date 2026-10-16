import { z } from 'zod'

export const decodedSseEventSchema = z.object({ id: z.number().int().positive(), event: z.string(), data: z.record(z.string(), z.unknown()) })
export type DecodedSseEvent = z.infer<typeof decodedSseEventSchema>
