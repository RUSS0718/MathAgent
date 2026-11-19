import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const root = fileURLToPath(new URL('../deeptutor-preview/', import.meta.url))
export default defineConfig({
  root,
  base: '/dashboard-assets/workbench/',
  plugins: [vue()],
  resolve: { alias: { '@': root } },
})
