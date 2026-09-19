import { test, expect } from '@playwright/test'

// The Tencent provider is retained and must keep driving the same workspace.
// Only its external boundary is stubbed; everything else is the real app.

const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAABQAAAAUCAIAAAAC64paAAAALElEQVR4nGP8//8/A7mAiWydDKOaSQZMpGtBgFHNJAImUjUgg1HNJAKKAgwAnKADJa4TmNgAAAAASUVORK5CYII=',
  'base64',
)

test('腾讯云 Provider 仍可完成上传、批改与刷新恢复', async ({ page }) => {
  await page.goto('/register')
  await page.getByLabel('用户名', { exact: true }).fill('tencent_' + Date.now())
  await page.getByLabel('密码', { exact: true }).fill('Test-password-12345')
  await page.getByLabel('确认密码', { exact: true }).fill('Test-password-12345')
  await page.getByRole('button', { name: '创建账号' }).click()
  await expect(page).toHaveURL('/app')
  await page.getByRole('button', { name: '新建备考计划' }).click()
  await page.getByLabel('课程名称').fill('大学物理')
  await page.getByLabel('考试日期').fill('2099-06-25')
  await page.getByRole('button', { name: '保存并开始诊断' }).click()
  await expect(page).toHaveURL(/\/app\/exams\//)

  await expect(page.getByTestId('marking-provider')).toContainText('腾讯云')
  await page.getByLabel('选择答题图片').setInputFiles({ name: 'page.png', mimeType: 'image/png', buffer: PNG })
  await page.getByRole('button', { name: '上传并开始批改' }).click()

  await expect(page.getByTestId('page-status')).toHaveText('批改完成', { timeout: 25000 })
  // Same unified result component, so the same per-question evidence is shown.
  await expect(page.getByTestId('mark-question')).toHaveCount(3)
  await expect(page.getByTestId('mark-provenance')).toContainText('腾讯云')
  const verdicts = page.getByTestId('mark-verdict')
  await expect(verdicts.nth(0)).toHaveText('错误')
  await expect(verdicts.nth(1)).toHaveText('正确')
  await expect(page.getByTestId('mark-summary')).toContainText('未计算百分制分数')

  await page.reload()
  await expect(page.getByTestId('page-status')).toHaveText('批改完成')
  await expect(page.getByTestId('marking-report')).toBeVisible()
  await page.screenshot({ path: '../artifacts/marking-tencent.png', fullPage: true })
})
