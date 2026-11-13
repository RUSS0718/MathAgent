import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './browser', testMatch: 'submission-recovery.spec.ts', workers: 1,
  outputDir: '../../../../artifacts/issue-171-work/browser',
  use: { baseURL: 'http://127.0.0.1:5187', browserName: 'chromium' },
  webServer: { command: 'npm run dev -- --host 127.0.0.1 --port 5187',
    url: 'http://127.0.0.1:5187/dashboard-assets/', reuseExistingServer: false },
})
