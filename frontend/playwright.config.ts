import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  // These specs drive the marking backend, which the default server does not run;
  // they have their own configs (playwright.marking*.config.ts).
  testIgnore: ['**/failure.spec.ts', '**/marking.spec.ts', '**/marking-unconfigured.spec.ts'],
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  reporter: [['list'], ['json', { outputFile: '../artifacts/browser-results.json' }]],
  use: { baseURL: 'http://127.0.0.1:5174', screenshot: 'only-on-failure', trace: 'retain-on-failure', launchOptions: { channel: 'chrome' } },
  webServer: [
    { command: '"..\\backend\\.venv\\Scripts\\python.exe" ../scripts/browser_test_server.py', url: 'http://127.0.0.1:8001/api/v1/health', reuseExistingServer: false, env:{ ALLOWED_ORIGINS:'http://127.0.0.1:5174' } },
    { command: 'npm run dev', url: 'http://127.0.0.1:5174', reuseExistingServer: false, env:{ FRONTEND_PORT:'5174', API_TARGET:'http://127.0.0.1:8001' } },
  ],
})
