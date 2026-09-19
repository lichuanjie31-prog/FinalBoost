import { defineConfig } from '@playwright/test'
import base from './playwright.config'

// Qwen selected as provider but with no API key: the UI must say so instead of
// falling back to a fabricated score.
export default defineConfig({
  ...base,
  testMatch: '**/marking-unconfigured-qwen.spec.ts',
  testIgnore: [],
  reporter: [['list'], ['json', { outputFile: '../artifacts/browser-marking-unconfigured-qwen-results.json' }]],
  use: { ...base.use, baseURL: 'http://127.0.0.1:5178' },
  webServer: [
    {
      command: '"..\\backend\\.venv\\Scripts\\python.exe" ../scripts/browser_marking_server.py',
      url: 'http://127.0.0.1:8005/api/v1/health',
      reuseExistingServer: false,
      env: {
        ALLOWED_ORIGINS: 'http://127.0.0.1:5178',
        PORT: '8005',
        MARKING_MODE: 'qwen',
        MARKING_PROVIDER: 'qwen',
        // Blank credentials guarantee the unconfigured state regardless of host env.
        DASHSCOPE_API_KEY: '',
        EMBEDDING_API_KEY: '',
      },
    },
    { command: 'npm run dev', url: 'http://127.0.0.1:5178', reuseExistingServer: false, env: { FRONTEND_PORT: '5178', API_TARGET: 'http://127.0.0.1:8005' } },
  ],
})
