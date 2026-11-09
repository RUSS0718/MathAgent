import { defineConfig } from '@playwright/test'

const browserRunId = `run-${new Date().toISOString().replace(/[:.]/g, '-')}`

export default defineConfig({
  testDir: './tests/browser', testMatch: 'faithful-s09.spec.ts', workers: 1,
  outputDir: `../../../artifacts/faithful-s09-browser-${browserRunId}`,
  preserveOutput: 'always', reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5189', browserName: 'chromium', locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai', colorScheme: 'light', reducedMotion: 'reduce',
    trace: 'retain-on-failure',
  },
  webServer: [{
    command: 'npm run dev -- --host 127.0.0.1 --port 5189',
    url: 'http://127.0.0.1:5189/dashboard-assets/',
    env: { VITE_FLASK_ORIGIN: 'http://127.0.0.1:18090' },
    reuseExistingServer: false,
  }],
})
