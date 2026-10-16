import { z } from 'zod'
export const filesResponseSchema = z.array(z.unknown())
export type FileResponse = z.infer<typeof filesResponseSchema>[number]
