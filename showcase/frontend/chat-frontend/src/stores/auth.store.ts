import { defineStore } from 'pinia'
import { api, setCsrfToken } from '../api/client'

export const useAuthStore = defineStore('auth', {
  state: () => ({ phase: 'checking' as 'checking' | 'ready' | 'signed_out', username: '', csrfToken: '' }),
  actions: {
    async check(): Promise<boolean> {
      const response = await api.checkAuth()
      this.username = response.username ?? 'local'
      this.csrfToken = response.csrf_token ?? ''
      setCsrfToken(this.csrfToken)
      this.phase = response.isLoggedIn ? 'ready' : 'signed_out'
      return response.isLoggedIn
    },
    async logout(): Promise<void> { await api.logout(); this.phase = 'signed_out' },
  },
})
