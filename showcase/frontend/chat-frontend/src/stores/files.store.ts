import { defineStore } from 'pinia'
import { api } from '../api/client'
export const useFilesStore = defineStore('files', { state: () => ({ items: [] as unknown[] }), actions: { async load(): Promise<void> { this.items = await api.listFiles() }, reset(): void { this.items = [] } } })
