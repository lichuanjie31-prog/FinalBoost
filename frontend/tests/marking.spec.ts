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

// 多页提交：第一页受理后必须立刻显示并进入轮询；第二页失败后重试，
// 不能把已受理的第一页再提交一次（否则供应商会被重复调用/重复计费）。
test('多页提交：第一页受理后立即显示并轮询，第二页失败重试不再提交第一页', async ({ page }) => {
  await createExam(page)
  await expect(page.getByTestId('marking-fixture')).toBeVisible()

  const posted: Array<{ pageIndex: number; requestKey: string }> = []
  await page.route('**/api/v1/marking/jobs', async route => {
    const request = route.request()
    if (request.method() !== 'POST') return route.continue()
    const body = request.postDataJSON() as { pageIndex: number; requestKey: string }
    posted.push(body)
    if (posted.length === 2) {
      // 注入第二页失败，验证已受理的第一页不受影响
      return route.fulfill({
        status: 500, contentType: 'application/json',
        body: JSON.stringify({ code: 50001, message: '第 2 页提交失败（用例注入）', data: null, requestId: 'test' }),
      })
    }
    return route.continue()
  })

  await page.getByLabel('选择答题图片').setInputFiles([page1, { ...page1, name: 'page2.png' }])
  await page.getByRole('button', { name: '上传并开始批改' }).click()

  await expect(page.getByRole('alert')).toContainText('第 2 页提交失败', { timeout: 20000 })

  // 第一页已受理：立即出现在结果列表，并继续轮询到完成
  const pages = page.getByTestId('marking-page')
  await expect(pages).toHaveCount(1)
  await expect(pages.first()).toContainText('第 1 页')
  await expect(pages.first().getByText('批改完成')).toBeVisible({ timeout: 20000 })

  // 重试：只提交尚未受理的第二页；第一页的请求总数保持为 1
  const before = posted.length
  await page.getByRole('button', { name: '上传并开始批改' }).click()
  await expect.poll(() => posted.slice(before).map(item => item.pageIndex), { timeout: 20000 }).toEqual([1])
  expect(posted.filter(item => item.pageIndex === 0)).toHaveLength(1)
  await expect(page.getByTestId('marking-page')).toHaveCount(2, { timeout: 20000 })
  await page.screenshot({ path: '../artifacts/marking-multipage-retry.png', fullPage: true })
})

// 批改完成后向助手追问：批改结果必须真的关联进对话上下文，
// 助手回答里要能看到这次批改的题目内容，而不是空手作答。
test('批改完成后在助手处追问错题，批改结果已进入对话上下文', async ({ page }) => {
  await createExam(page)
  const examId = page.url().split('/').pop()!
  await expect(page.getByTestId('marking-fixture')).toBeVisible()

  await page.getByLabel('选择答题图片').setInputFiles(page1)
  await page.getByRole('button', { name: '上传并开始批改' }).click()
  await expect(page.getByText('批改完成', { exact: true })).toBeVisible({ timeout: 20000 })
  await expect(page.getByText(/已关联所选批改结果/)).toBeVisible()

  const sent = page.waitForRequest(r => r.url().endsWith('/agent/chat') && r.method() === 'POST')
  await page.getByRole('button', { name: '分析这次判卷结果' }).click()
  const body = (await sent).postDataJSON()
  expect(body.examId).toBe(examId)
  expect(body.markingJobIds).toHaveLength(1)
  expect(body.gradingId).toBeUndefined()

  await expect(page.locator('.study-message.user')).toHaveCount(1)
  await expect(page.locator('.study-message.assistant')).toHaveCount(1)
  // 工具卡片里应当是本次批改的真实题目内容（fixture 数据集里的第 2 题）
  await expect(page.locator('.study-tool pre')).toContainText('判断级数敛散性')
  await page.screenshot({ path: '../artifacts/marking-ai-explain.png', fullPage: true })
})
