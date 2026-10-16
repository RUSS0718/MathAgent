import { z } from 'zod'

export const checkAuthResponseSchema = z.object({
  isLoggedIn: z.boolean(),
  username: z.string().optional(),
  csrf_token: z.string().optional(),
}).passthrough()
export const logoutResponseSchema = z.object({ success: z.boolean(), error: z.string().optional() }).passthrough()
export type CheckAuthResponse = z.infer<typeof checkAuthResponseSchema>
export type LogoutResponse = z.infer<typeof logoutResponseSchema>
