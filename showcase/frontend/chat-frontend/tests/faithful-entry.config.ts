import { defineConfig } from '@playwright/test'

/** Isolated frontend-only acceptance; all API responses are synthetic. */
export default defineConfig({
  testDir: './browser', testMatch: 'faithful-entry.spec.ts', workers: 1,
  outputDir: '../../../../artifacts/faithful-entry-browser',
  use: { baseURL: 'http://127.0.0.1:5186', browserName: 'chromium' },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5186',
    url: 'http://127.0.0.1:5186/dashboard-assets/', reuseExistingServer: false,
  },
})
