import { defineStore } from 'pinia'
import { api } from '../api/client'
import type { ChatMessageResponse } from '../api/sessions.schemas'

export const useSessionsStore = defineStore('sessions', {
  state: () => ({ items: [] as Array<{ id: string; preview: string; lastTime: string }>, currentId: null as string | null, messages: [] as ChatMessageResponse[] }),
  actions: {
    async loadList(): Promise<void> { this.items = (await api.listSessions()).map(([id, info]) => ({ id, preview: info.preview, lastTime: info.last_time })) },
    async create(): Promise<string> { const result = await api.newChat(); if (!result.success || !result.new_session_id) throw new Error(result.error ?? '创建会话失败'); this.currentId = result.new_session_id; this.messages = []; await this.loadList(); return result.new_session_id },
    async select(id: string): Promise<void> { const result = await api.loadSession(id); if (!result.success) throw new Error(result.error ?? '加载会话失败'); this.currentId = id; this.messages = result.messages ?? [] },
    async rename(id: string, title: string): Promise<void> { await api.changeSession(id, title); await this.loadList() },
    async remove(id: string): Promise<void> { await api.deleteSession(id); this.items = this.items.filter((item) => item.id !== id); if (this.currentId === id) { this.currentId = null; this.messages = [] } },
    addUser(text: string, jobId: string): void { this.messages.push({ sender: 'user', text, analysis_job_id: jobId }) },
    reset(): void { this.items = []; this.currentId = null; this.messages = [] },
  },
})
