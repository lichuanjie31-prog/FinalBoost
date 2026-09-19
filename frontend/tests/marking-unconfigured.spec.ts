import { test, expect } from '@playwright/test'

const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAABQAAAAUCAIAAAAC64paAAAALElEQVR4nGP8//8/A7mAiWydDKOaSQZMpGtBgFHNJAImUjUgg1HNJAKKAgwAnKADJa4TmNgAAAAASUVORK5CYII=',
  'base64',
)

test('缺少腾讯云凭据时明确提示尚未配置，且不生成示例分数', async ({ page }) => {
  await page.goto('/register')
  await page.getByLabel('用户名', { exact: true }).fill('nokey_' + Date.now())
  await page.getByLabel('密码', { exact: true }).fill('Test-password-12345')
  await page.getByLabel('确认密码', { exact: true }).fill('Test-password-12345')
  await page.getByRole('button', { name: '创建账号' }).click()
  await expect(page).toHaveURL('/app')
  await page.getByRole('button', { name: '新建备考计划' }).click()
  await page.getByLabel('课程名称').fill('线性代数')
  await page.getByLabel('考试日期').fill('2099-06-22')
  await page.getByRole('button', { name: '保存并开始诊断' }).click()
  await expect(page).toHaveURL(/\/app\/exams\//)

  // The real marking workspace is active and says it is not configured.
  const warning = page.getByTestId('marking-not-configured')
  await expect(warning).toBeVisible()
  await expect(warning).toContainText('尚未配置腾讯云凭据')
  await expect(warning).toContainText('不会生成示例分数')
  // The local demo must not be presented as a result either.
  await expect(page.getByText('模拟数据，仅用于流程联调')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '上传并开始批改' })).toBeDisabled()

  await page.getByLabel('选择答题图片').setInputFiles({ name: 'page.png', mimeType: 'image/png', buffer: PNG })
  await expect(page.getByRole('button', { name: '上传并开始批改' })).toBeDisabled()

  await page.screenshot({ path: '../artifacts/marking-not-configured.png', fullPage: true })
  await expect(page.getByTestId('marking-report')).toHaveCount(0)
  await expect(page.getByTestId('page-status')).toHaveCount(0)
})
