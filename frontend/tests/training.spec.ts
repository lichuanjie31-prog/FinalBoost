import { test, expect, type Page } from '@playwright/test'

async function registerAndDiagnose(page: Page) {
  const username = `train_${Date.now()}`
  await page.goto('/register')
  await page.getByLabel('用户名', { exact: true }).fill(username)
  await page.getByLabel('密码', { exact: true }).fill('Test-password-12345')
  await page.getByLabel('确认密码', { exact: true }).fill('Test-password-12345')
  await page.getByRole('button', { name: '创建账号' }).click()
  await expect(page).toHaveURL('/app')
  await page.getByRole('button', { name: '新建备考计划' }).click()
  await page.getByLabel('课程名称').fill('数据结构')
  await page.getByLabel('考试日期').fill('2099-06-20')
  await page.getByLabel('目标分数').fill('85')
  await page.getByRole('button', { name: '保存并开始诊断' }).click()
  await expect(page).toHaveURL(/\/app\/exams\//)
  await page.getByLabel('选择答题图片').setInputFiles({ name: 'answer.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAABQAAAAUCAIAAAAC64paAAAALElEQVR4nGP8//8/A7mAiWydDKOaSQZMpGtBgFHNJAImUjUgg1HNJAKKAgwAnKADJa4TmNgAAAAASUVORK5CYII=', 'base64') })
  await page.getByRole('button', { name: '上传并开始模拟判卷' }).click()
  await expect(page.getByText('判卷完成', { exact: true }).first()).toBeVisible({ timeout: 15000 })
  await page.getByRole('button', { name: '查看示例诊断' }).first().click()
  await expect(page.getByRole('heading', { name: '示例诊断报告' })).toBeVisible()
}

async function answerCurrentStage(page: Page, count: number) {
  const items = page.locator('.stage-panel .question-item')
  await expect(items).toHaveCount(count)
  for (let i = 0; i < count; i++) {
    const item = items.nth(i)
    await item.locator('.option').first().click()
    await item.getByRole('button', { name: '提交答案' }).click()
    await expect(item.locator('.attempt-result')).toBeVisible({ timeout: 10000 })
  }
  await page.getByRole('button', { name: '完成本阶段，进入下一阶段' }).click()
}

test('从诊断薄弱点创建专项训练并完成五阶段', async ({ page }) => {
  test.setTimeout(90_000)
  await registerAndDiagnose(page)
  await page.getByRole('button', { name: '开始专项训练' }).first().click()
  await expect(page).toHaveURL(/\/app\/trainings\//)
  await expect(page.getByRole('heading', { name: /专项突破/ })).toBeVisible()

  await expect(page.locator('.stage-panel h2')).toHaveText('题型速记')
  await page.getByRole('button', { name: '完成本阶段，进入下一阶段' }).click()
  await expect(page.locator('.stage-panel h2')).toHaveText('AI 带做')

  await answerCurrentStage(page, 2)
  await expect(page.locator('.stage-panel h2')).toHaveText('简单真题')

  await answerCurrentStage(page, 3)
  await expect(page.locator('.stage-panel h2')).toHaveText('中等真题')

  await answerCurrentStage(page, 2)
  await expect(page.locator('.stage-panel h2')).toHaveText('掌握度检测')

  await page.getByRole('button', { name: '生成检测题' }).click()
  await page.locator('.quiz-input').fill('核心思路是先确定最短距离，再松弛相邻边，适用于非负权图。')
  await page.getByRole('button', { name: '提交检测答案' }).click()
  await expect(page.locator('.attempt-result')).toContainText('已达标', { timeout: 10000 })

  await page.getByRole('button', { name: '生成 PDF' }).click()
  await expect(page.getByRole('button', { name: /下载 .*\.pdf/ })).toBeVisible({ timeout: 15000 })
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /下载 .*\.pdf/ }).click()])
  expect(download.suggestedFilename()).toContain('.pdf')

  await page.getByRole('link', { name: '专项训练' }).click()
  await expect(page.getByRole('heading', { name: '专项训练' })).toBeVisible()
  await expect(page.getByText('5 / 5 阶段')).toBeVisible()
  await page.screenshot({ path: '../artifacts/training-desktop.png', fullPage: true })
})
