import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './browser', testMatch: 'faithful-status.spec.ts', workers: 1,
  outputDir: '../../../../artifacts/issue-182/frontend-browser',
  use: { baseURL: 'http://127.0.0.1:5188', browserName: 'chromium' },
  webServer: { command: 'npm run dev -- --host 127.0.0.1 --port 5188', url: 'http://127.0.0.1:5188/dashboard-assets/', reuseExistingServer: false },
})
