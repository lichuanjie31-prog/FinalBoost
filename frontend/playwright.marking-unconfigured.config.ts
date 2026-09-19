import { defineConfig } from '@playwright/test'
import base from './playwright.config'

// Real marking mode with no credentials: proves the UI says so instead of
// falling back to a fabricated score.
export default defineConfig({
  ...base,
  testMatch: '**/marking-unconfigured.spec.ts',
  testIgnore: [],
  reporter: [['list'], ['json', { outputFile: '../artifacts/browser-marking-unconfigured-results.json' }]],
  use: { ...base.use, baseURL: 'http://127.0.0.1:5176' },
  webServer: [
    {
      command: '"..\\backend\\.venv\\Scripts\\python.exe" ../scripts/browser_marking_server.py',
      url: 'http://127.0.0.1:8003/api/v1/health',
      reuseExistingServer: false,
      env: {
        ALLOWED_ORIGINS: 'http://127.0.0.1:5176',
        PORT: '8003',
        MARKING_MODE: 'tencent',
        // Blank credentials guarantee the unconfigured state regardless of the host env.
        TENCENTCLOUD_SECRET_ID: '',
        TENCENTCLOUD_SECRET_KEY: '',
      },
    },
    { command: 'npm run dev', url: 'http://127.0.0.1:5176', reuseExistingServer: false, env: { FRONTEND_PORT: '5176', API_TARGET: 'http://127.0.0.1:8003' } },
  ],
})
