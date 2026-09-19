import { defineConfig } from '@playwright/test'
import base from './playwright.config'

// Proves the retained Tencent provider still drives the same workspace and the
// same result component. Its boundary is stubbed exactly as the Qwen suite's is.
export default defineConfig({
  ...base,
  testMatch: '**/marking-tencent.spec.ts',
  testIgnore: [],
  reporter: [['list'], ['json', { outputFile: '../artifacts/browser-marking-tencent-results.json' }]],
  use: { ...base.use, baseURL: 'http://127.0.0.1:5177' },
  webServer: [
    {
      command: '"..\\backend\\.venv\\Scripts\\python.exe" ../scripts/browser_marking_server.py',
      url: 'http://127.0.0.1:8004/api/v1/health',
      reuseExistingServer: false,
      env: {
        ALLOWED_ORIGINS: 'http://127.0.0.1:5177',
        PORT: '8004',
        MARKING_MODE: 'fixture',
        // 测试固定用示例对话：不继承开发者 .env 里的真实模型 Key
        LLM_API_KEY: '',
        MARKING_PROVIDER: 'tencent',
        MARKING_SUBMIT_INTERVAL: '0.2',
        MARKING_POLL_INTERVAL: '0.2',
        MARKING_FIXTURE_STAGES: '1',
      },
    },
    { command: 'npm run dev', url: 'http://127.0.0.1:5177', reuseExistingServer: false, env: { FRONTEND_PORT: '5177', API_TARGET: 'http://127.0.0.1:8004' } },
  ],
})
