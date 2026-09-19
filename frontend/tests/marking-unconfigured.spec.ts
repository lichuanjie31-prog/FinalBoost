import { test } from '@playwright/test'
import { runUnconfiguredCheck } from './unconfigured-flow'

test('缺少腾讯云凭据时明确提示尚未配置，且不生成示例分数', async ({ page }) => {
  await runUnconfiguredCheck(page, '腾讯云', '线性代数')
})
