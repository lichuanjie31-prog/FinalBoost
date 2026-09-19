import { defineConfig } from '@playwright/test'
import base from './playwright.config'

// Runs the marking acceptance suite against a real local backend whose only
// substituted component is the Tencent SDK boundary (MARKING_MODE=fixture).
export default defineConfig({
  ...base,
  testMatch: '**/marking.spec.ts',
  testIgnore: [],
  reporter: [['list'], ['json', { outputFile: '../artifacts/browser-marking-results.json' }]],
  use: { ...base.use, baseURL: 'http://127.0.0.1:5175' },
  webServer: [
    {
      command: '"..\\backend\\.venv\\Scripts\\python.exe" ../scripts/browser_marking_server.py',
      url: 'http://127.0.0.1:8002/api/v1/health',
      reuseExistingServer: false,
      env: {
        ALLOWED_ORIGINS: 'http://127.0.0.1:5175',
        MARKING_MODE: 'fixture',
        MARKING_PROVIDER: 'qwen',
        // Pinned so the assertions cannot drift with a developer's backend/.env.
        QWEN_MARKING_MODEL: 'qwen3-vl-plus',
        // The vendor's 10-per-minute limit is respected by default; this suite
        // lowers the pacing so the flow completes inside a test timeout.
        MARKING_SUBMIT_INTERVAL: '0.2',
        MARKING_POLL_INTERVAL: '0.2',
        MARKING_FIXTURE_STAGES: '1',
        MARKING_FIXTURE_CONTROL: '../artifacts/marking-fixture-control.json',
      },
    },
    { command: 'npm run dev', url: 'http://127.0.0.1:5175', reuseExistingServer: false, env: { FRONTEND_PORT: '5175', API_TARGET: 'http://127.0.0.1:8002' } },
  ],
})
