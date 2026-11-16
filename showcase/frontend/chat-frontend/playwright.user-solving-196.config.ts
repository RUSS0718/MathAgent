import { defineConfig } from '@playwright/test'
export default defineConfig({
 testDir: './tests/browser', testMatch: 'user-solving-196-http.spec.ts', workers: 1,
 outputDir: '../../../artifacts/user-solving-196/http', reporter: 'list',
 use: { baseURL: 'http://127.0.0.1:5176', browserName: 'chromium', locale: 'zh-CN', trace: 'retain-on-failure' },
 webServer: [
 { command: 'uv run python tests/browser/user_solving_196_server.py', url: 'http://127.0.0.1:8096/health', reuseExistingServer: false },
 { command: 'npm run dev -- --host 127.0.0.1 --port 5176', url: 'http://127.0.0.1:5176/dashboard-assets/', env: { VITE_FLASK_ORIGIN: 'http://127.0.0.1:8096' }, reuseExistingServer: false },
 ],
})
