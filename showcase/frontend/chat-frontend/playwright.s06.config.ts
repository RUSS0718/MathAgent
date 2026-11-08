import { defineConfig } from '@playwright/test'

const browserRunId = `run-${new Date().toISOString().replace(/[:.]/g, '-')}`

export default defineConfig({
  testDir: './tests/browser', testMatch: 'faithful-s06.spec.ts', workers: 1,
  outputDir: `../../../artifacts/faithful-s06-browser-${browserRunId}`, reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:5188', browserName: 'chromium', locale: 'zh-CN', trace: 'retain-on-failure' },
  webServer: [
    { command: 'uv run python tests/browser/product_server.py', url: 'http://127.0.0.1:8091/health', reuseExistingServer: false },
    { command: 'npm run dev -- --host 127.0.0.1 --port 5188', url: 'http://127.0.0.1:5188/dashboard-assets/', env: { VITE_FLASK_ORIGIN: 'http://127.0.0.1:8091' }, reuseExistingServer: false },
  ],
})
