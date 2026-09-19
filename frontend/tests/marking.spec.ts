import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

// The backend reads the same file to decide which vendor behaviour to replay, so
// a vendor failure can be forced and then recovered without restarting anything.
const CONTROL = path.resolve(process.cwd(), '../artifacts/marking-fixture-control.json')
const scenario = (name: string) => {
  fs.mkdirSync(path.dirname(CONTROL), { recursive: true })
  fs.writeFileSync(CONTROL, JSON.stringify({ scenario: name }))
}

const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAABQAAAAUCAIAAAAC64paAAAALElEQVR4nGP8//8/A7mAiWydDKOaSQZMpGtBgFHNJAImUjUgg1HNJAKKAgwAnKADJa4TmNgAAAAASUVORK5CYII=',
  'base64',
)
const page1 = { name: 'page1.png', mimeType: 'image/png', buffer: PNG }

test.beforeAll(() => fs.rmSync(CONTROL, { force: true }))
test.afterAll(() => fs.rmSync(CONTROL, { force: true }))

async function createExam(page: import('@playwright/test').Page) {
  await page.goto('/register')
  await page.getByLabel('用户名', { exact: true }).fill('mark_' + Date.now())
  await page.getByLabel('密码', { exact: true }).fill('Test-password-12345')
  await page.getByLabel('确认密码', { exact: true }).fill('Test-password-12345')
  await page.getByRole('button', { name: '创建账号' }).click()
  await expect(page).toHaveURL('/app')
  await page.getByRole('button', { name: '新建备考计划' }).click()
  await page.getByLabel('课程名称').fill('高等数学')
  await page.getByLabel('考试日期').fill('2099-06-20')
  await page.getByRole('button', { name: '保存并开始诊断' }).click()
  await expect(page).toHaveURL(/\/app\/exams\//)
}

test('按页展示千问批改的正误、解析与知识点，刷新不丢任务', async ({ page }) => {
  await createExam(page)
  // The real marking workspace is live, not the labelled local demo.
  await expect(page.getByTestId('marking-fixture')).toBeVisible()
  await expect(page.getByText('模拟数据，仅用于流程联调')).toHaveCount(0)

  await page.getByLabel('选择答题图片').setInputFiles(page1)
  await page.getByRole('button', { name: '上传并开始批改' }).click()

  await expect(page.getByTestId('marking-page')).toHaveCount(1)
  const status = page.getByTestId('page-status')
  await expect(status).toHaveText(/排队中|处理中/)
  await expect(status).toHaveText('批改完成', { timeout: 25000 })

  // Parent question plus its sub-question are both rendered.
  await expect(page.getByTestId('mark-question')).toHaveCount(3)
  await expect(page.getByTestId('mark-stem').first()).toContainText('求不定积分')
  await expect(page.getByTestId('mark-stem').nth(1)).toContainText('第 (1) 问')

  // Per-answer evidence: handwriting, verdict, reference answer, analysis, points.
  await expect(page.getByTestId('mark-handwriting').first()).toHaveText('x^2/2')
  const verdicts = page.getByTestId('mark-verdict')
  await expect(verdicts).toHaveCount(3)
  await expect(verdicts.nth(0)).toHaveText('错误')
  await expect(verdicts.nth(1)).toHaveText('正确')
  await expect(verdicts.nth(2)).toHaveText('错误')
  await expect(page.getByTestId('mark-right-answer').first()).toHaveText('x^2/2 + C')
  await expect(page.getByTestId('mark-analysis').first()).toContainText('漏写积分常数')
  await expect(page.getByTestId('mark-knowledge').first()).toContainText('不定积分')
  // The error reason and the provider that produced the result are both visible.
  await expect(page.getByTestId('mark-error-reason').first()).toContainText('漏写积分常数 C')
  await expect(page.getByTestId('mark-provenance')).toContainText('千问视觉')
  await expect(page.getByTestId('mark-provenance')).toContainText('qwen3-vl-plus')
  await expect(page.getByTestId('page-provenance')).toContainText('Token')
  // Coordinates stay text-only, as the notice says.
  await expect(page.getByTestId('marking-report').first()).toContainText('原卷坐标批注仍在测试中')

  // No percentage score is invented, and the old mock diagnosis is gone.
  await expect(page.getByTestId('mark-summary')).toContainText('正确 1')
  await expect(page.getByTestId('mark-summary')).toContainText('错误 2')
  await expect(page.getByTestId('mark-summary')).toContainText('未计算百分制分数')
  await expect(page.getByRole('button', { name: '查看示例诊断' })).toHaveCount(0)

  await page.screenshot({ path: '../artifacts/marking-result-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 375, height: 900 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: '../artifacts/marking-result-mobile.png', fullPage: true })

  // A refresh recovers the page and its result from persistence.
  await page.reload()
  await expect(page.getByTestId('page-status')).toHaveText('批改完成')
  await expect(page.getByTestId('marking-report')).toBeVisible()
  await expect(page.getByTestId('mark-verdict')).toHaveCount(3)
})

test('供应商失败显示失败且不给示例分数，恢复后继续成功', async ({ page }) => {
  await createExam(page)
  await page.setViewportSize({ width: 768, height: 900 })

  await page.getByLabel('选择答题图片').setInputFiles(page1)
  await page.getByRole('button', { name: '上传并开始批改' }).click()
  await expect(page.getByTestId('page-status')).toHaveText('批改完成', { timeout: 25000 })

  // Force a vendor-side failure on the next page.
  scenario('provider_error')
  await page.getByLabel('选择答题图片').setInputFiles({ ...page1, name: 'page2.png' })
  await page.getByRole('button', { name: '上传并开始批改' }).click()
  await expect(page.getByTestId('marking-page')).toHaveCount(2)

  const failed = page.getByTestId('marking-page').nth(1)
  await expect(failed.getByTestId('page-status')).toHaveText('批改失败', { timeout: 25000 })
  await expect(failed.getByTestId('page-error-code')).toContainText('qwen:BadResponse')
  // A failure never carries a score or a result body.
  await expect(failed.getByTestId('marking-report')).toHaveCount(0)
  await expect(page.getByTestId('marking-failed-note')).toContainText('1 页批改失败')
  await page.screenshot({ path: '../artifacts/marking-failure.png', fullPage: true })

  // Recover: the next page succeeds and the earlier failure is untouched.
  scenario('success')
  await page.getByLabel('选择答题图片').setInputFiles({ ...page1, name: 'page3.png' })
  await page.getByRole('button', { name: '上传并开始批改' }).click()
  await expect(page.getByTestId('marking-page')).toHaveCount(3)
  const recovered = page.getByTestId('marking-page').nth(2)
  await expect(recovered.getByTestId('page-status')).toHaveText('批改完成', { timeout: 25000 })
  await expect(recovered.getByTestId('marking-report')).toBeVisible()
  await expect(page.getByTestId('marking-page').nth(1).getByTestId('page-status')).toHaveText('批改失败')
  await page.screenshot({ path: '../artifacts/marking-recovered.png', fullPage: true })
})
