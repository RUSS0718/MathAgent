import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  return { base: '/dashboard-assets/', plugins: [vue()], server: { port: 5174, strictPort: true, proxy: { '/api': { target: env.VITE_FLASK_ORIGIN || 'http://127.0.0.1:8090', changeOrigin: true } } }, build: { manifest: true } }
})
