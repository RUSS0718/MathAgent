import { defineStore } from 'pinia'
export const useComposerStore = defineStore('composer', { state: () => ({ draft: '', sending: false }), actions: { reset(): void { this.draft = ''; this.sending = false } } })
