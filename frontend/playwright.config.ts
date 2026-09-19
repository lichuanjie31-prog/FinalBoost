import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  // These specs drive a marking backend in a specific provider mode, which the
  // default server does not run; each has its own config (playwright.marking*.config.ts).
  testIgnore: [
    '**/failure.spec.ts',
    '**/marking.spec.ts',
    '**/marking-tencent.spec.ts',
    '**/marking-unconfigured.spec.ts',
    '**/marking-unconfigured-qwen.spec.ts',
  ],
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  reporter: [['list'], ['json', { outputFile: '../artifacts/browser-results.json' }]],
  use: { baseURL: 'http://127.0.0.1:5174', screenshot: 'only-on-failure', trace: 'retain-on-failure', launchOptions: { channel: 'chrome' } },
  webServer: [
    // These specs cover the labelled local demo, so marking is pinned off here.
    // Without this the suite would inherit whatever MARKING_* a developer's
    // backend/.env sets (load_dotenv does not override a real env var).
    { command: '"..\\backend\\.venv\\Scripts\\python.exe" ../scripts/browser_test_server.py', url: 'http://127.0.0.1:8001/api/v1/health', reuseExistingServer: false, env:{ ALLOWED_ORIGINS:'http://127.0.0.1:5174', MARKING_MODE:'disabled' } },
    { command: 'npm run dev', url: 'http://127.0.0.1:5174', reuseExistingServer: false, env:{ FRONTEND_PORT:'5174', API_TARGET:'http://127.0.0.1:8001' } },
  ],
})
