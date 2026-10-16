import { z } from 'zod'
export const fileSchema = z.object({ file_id: z.string(), reference: z.string(), mime: z.literal('image/png'), size: z.number(), sha256: z.string(), status: z.string() })
export const filesResponseSchema = z.array(fileSchema)
export const uploadResponseSchema = z.object({ file: fileSchema })
export type FileResponse = z.infer<typeof fileSchema>
