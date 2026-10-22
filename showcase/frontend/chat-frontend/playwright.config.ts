import { defineConfig } from '@playwright/test'

/** A separate test server and synthetic API data keep screenshots repeatable. */
export default defineConfig({
  testDir: './tests/browser',
  outputDir: '../../../artifacts/ui-unification/browser',
  snapshotPathTemplate: '{testDir}/snapshots/{platform}/{arg}{ext}',
  fullyParallel: true,
  workers: 2,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5176',
    browserName: 'chromium',
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 1,
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    colorScheme: 'light',
    reducedMotion: 'reduce',
    trace: 'retain-on-failure',
  },
  webServer: [{
    command: 'npm run dev -- --host 127.0.0.1 --port 5176',
    url: 'http://127.0.0.1:5176/dashboard-assets/',
    reuseExistingServer: false,
  }, {
    command: 'uv run python tests/browser/legacy_server.py',
    url: 'http://127.0.0.1:5177/demo',
    reuseExistingServer: false,
  }],
})
