import { defineConfig } from '@playwright/test'

const browserRunId = `run-${new Date().toISOString().replace(/[:.]/g, '-')}`

export default defineConfig({
  testDir: './tests/browser', testMatch: 'faithful-f7.spec.ts', workers: 1,
  timeout: 120_000,
  outputDir: `../../../artifacts/faithful-f7-browser-${browserRunId}`,
  preserveOutput: 'always', reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:8096', browserName: 'chromium',
    viewport: { width: 1440, height: 1000 }, locale: 'zh-CN',
    timezoneId: 'Europe/Paris', colorScheme: 'light', reducedMotion: 'reduce',
    trace: 'retain-on-failure',
  },
  webServer: [{
    command: 'npm run build && uv run python tests/browser/faithful_f7_server.py',
    env: { VITE_F7_SYSTEM_VIEW_ENABLED: 'true' },
    url: 'http://127.0.0.1:8096/__test__/f7/health', reuseExistingServer: false,
  }],
})
