import { test } from '@playwright/test'
import { runUnconfiguredCheck } from './unconfigured-flow'

test('缺少千问 API Key 时明确提示尚未配置，且不生成示例分数', async ({ page }) => {
  await runUnconfiguredCheck(page, '千问视觉', '概率论')
})
