import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './tests/browser', testMatch: 'routes.spec.ts', workers: 1,
  outputDir: `../../../artifacts/routes-browser-${Date.now()}`, reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:5287', browserName: 'chromium', locale: 'zh-CN', trace: 'retain-on-failure' },
  webServer: [
    { command: 'uv run python tests/browser/route_server.py', url: 'http://127.0.0.1:8195/health', reuseExistingServer: false },
    { command: 'npm run dev -- --host 127.0.0.1 --port 5287', url: 'http://127.0.0.1:5287/dashboard-assets/', env: { VITE_FLASK_ORIGIN: 'http://127.0.0.1:8195' }, reuseExistingServer: false },
  ],
})
