import { defineConfig } from '@playwright/test'
import base from './playwright.config'

export default defineConfig({
  ...base,
  testMatch: '**/failure.spec.ts',
  testIgnore: [],
  reporter: [['list'], ['json', { outputFile:'../artifacts/browser-failure-results.json' }]],
  webServer: [
    { command:'"..\\backend\\.venv\\Scripts\\python.exe" ../scripts/browser_test_server.py', url:'http://127.0.0.1:8001/api/v1/health', reuseExistingServer:false, env:{ ALLOWED_ORIGINS:'http://127.0.0.1:5174', MOCK_SCENARIO:'unreadable' } },
    { command:'npm run dev', url:'http://127.0.0.1:5174', reuseExistingServer:false, env:{ FRONTEND_PORT:'5174', API_TARGET:'http://127.0.0.1:8001' } },
  ],
})
