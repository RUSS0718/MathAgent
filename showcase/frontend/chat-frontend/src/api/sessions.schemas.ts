import { z } from 'zod'

const sessionInfoSchema = z.object({ preview: z.string(), last_time: z.string() }).passthrough()
export const sessionsResponseSchema = z.array(z.tuple([z.string(), sessionInfoSchema]))
export const newChatResponseSchema = z.object({ success: z.boolean(), new_session_id: z.string().optional(), error: z.string().optional() }).passthrough()
export const chatMessageSchema = z.object({
  sender: z.enum(['user', 'ai']), text: z.string(), analysis_job_id: z.string().nullable().optional(), created_at: z.string().optional(),
}).passthrough()
export const loadSessionResponseSchema = z.object({ success: z.boolean(), messages: z.array(chatMessageSchema).optional(), error: z.string().optional() }).passthrough()
export const changeSessionResponseSchema = z.object({ success: z.boolean(), session_id: z.string().optional(), title: z.string().optional(), error: z.string().optional() }).passthrough()
export const deleteSessionResponseSchema = z.object({ success: z.boolean(), error: z.string().optional() }).passthrough()
export type SessionsResponse = z.infer<typeof sessionsResponseSchema>
export type NewChatResponse = z.infer<typeof newChatResponseSchema>
export type LoadSessionResponse = z.infer<typeof loadSessionResponseSchema>
export type ChatMessageResponse = z.infer<typeof chatMessageSchema>
export type ChangeSessionResponse = z.infer<typeof changeSessionResponseSchema>
export type DeleteSessionResponse = z.infer<typeof deleteSessionResponseSchema>
