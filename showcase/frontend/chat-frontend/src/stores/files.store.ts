import { defineStore } from 'pinia'
import { api } from '../api/client'
export const useFilesStore = defineStore('files', { state: () => ({ items: [] as Awaited<ReturnType<typeof api.listFiles>>, enabled: false }), actions: { async load(): Promise<void> { this.items = await api.listFiles() }, async upload(file: File): Promise<void> { const result = await api.uploadFile(file); this.items.push(result.file) }, async remove(id: string): Promise<void> { await api.deleteFile(id); this.items = this.items.filter((item) => item.file_id !== id) }, reset(): void { this.items = [] } } })
