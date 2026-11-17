import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/browser',
  testMatch: 'role-stage-saved.spec.ts',
  outputDir: '../../../artifacts/role-stage-199/saved-browser',
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5183', browserName: 'chromium',
    viewport: { width: 1440, height: 1000 }, locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai', trace: 'retain-on-failure',
  },
  webServer: [{
    command: 'uv run python tests/browser/role-stage-saved-server.py',
    url: 'http://127.0.0.1:5182/health', reuseExistingServer: false,
  }, {
    command: 'npm run dev -- --host 127.0.0.1 --port 5183',
    env: { VITE_FLASK_ORIGIN: 'http://127.0.0.1:5182' },
    url: 'http://127.0.0.1:5183/dashboard-assets/', reuseExistingServer: false,
  }],
})
