import { expect, test } from '@playwright/test'

// 集成验收：三个板块（题库 / 专项训练 / 最终模拟）都能从侧边栏真正进入并渲染，
// 而不是只保证代码能编译。题库与专项训练来自 master / feature/training，
// 最终模拟来自 feature/mock-exam，三条分支的路由与导航在这里汇合。

const password = 'Test-password-12345'

async function register(page: import('@playwright/test').Page, username: string) {
  await page.goto('/register')
  await page.getByLabel('用户名', { exact: true }).fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByLabel('确认密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '创建账号' }).click()
  await expect(page).toHaveURL('/app')
}

test('题库、专项训练、最终模拟三个板块都能进入', async ({ page }) => {
  await register(page, 'boards_' + Date.now())

  // 先建一场考试：「最终模拟」按考试组织，没有考试就进不到模拟卷。
  await page.getByRole('button', { name: '新建备考计划' }).click()
  await page.getByLabel('课程名称').fill('数据结构')
  await page.getByLabel('考试日期').fill('2099-06-20')
  await page.getByRole('button', { name: '保存并开始诊断' }).click()
  await expect(page).toHaveURL(/\/app\/exams\//)
  const examId = page.url().split('/').pop()!

  // 私人题库
  await page.getByRole('link', { name: '私人题库', exact: true }).click()
  await expect(page).toHaveURL('/app/question-bank')
  await expect(page.getByRole('heading', { name: '私人题库', exact: true })).toBeVisible()

  // 公共题库
  await page.getByRole('link', { name: '公共题库', exact: true }).click()
  await expect(page).toHaveURL('/app/question-bank/public')
  await expect(page.getByRole('heading', { name: '公共题库', exact: true })).toBeVisible()

  // 专项训练（来自 feature/training，导航里不再是「规划中」占位）
  await page.getByRole('link', { name: '专项训练', exact: true }).click()
  await expect(page).toHaveURL('/app/trainings')
  await expect(page.getByRole('heading', { name: '专项训练', exact: true })).toBeVisible()

  // 最终模拟板块首页（来自 feature/mock-exam）
  await page.getByRole('link', { name: '最终模拟', exact: true }).click()
  await expect(page).toHaveURL('/app/mock')
  await expect(page.getByRole('heading', { name: '最终模拟', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '数据结构', exact: true })).toBeVisible()

  // 从板块进入这场考试的模拟卷：证明路由与数据都真的接上了。
  // 按钮文案随模拟卷状态变化（开始第一套 / 继续作答 / 查看 …），所以按 href 定位。
  await page.locator(`a[href="/app/exams/${examId}/mock"]`).first().click()
  await expect(page).toHaveURL(new RegExp(`/app/exams/${examId}/mock$`))
  await expect(page.getByRole('heading', { name: /最终模拟 · 数据结构/ })).toBeVisible()
  await expect(page.getByRole('heading', { name: '试卷', exact: true })).toBeVisible()

  await page.screenshot({ path: '../artifacts/integration-boards.png', fullPage: true })
})
