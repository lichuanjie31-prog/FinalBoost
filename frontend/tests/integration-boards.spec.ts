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

// 组卷来源是 backend/app/mock_bank.py 的内置题库，答案固定；
// 这里按它列出标准答案，用来验证「不同作答得到不同评分」。
// 若内置题库改动，本用例会失败——这正是提示需要同步验收数据的信号。
const CORRECT = { demo_q1: 'B', demo_q2: 'C', demo_q3: 'C', demo_q4: 'C' }
const WRONG_ALL_A: Record<string, string> = { demo_q1: 'A', demo_q2: 'A', demo_q3: 'A', demo_q4: 'A' }

async function createExam(page: import('@playwright/test').Page) {
  await register(page, 'mockexam_' + Date.now())
  await page.getByRole('button', { name: '新建备考计划' }).click()
  await page.getByLabel('课程名称').fill('数据结构')
  await page.getByLabel('考试日期').fill('2099-06-20')
  await page.getByRole('button', { name: '保存并开始诊断' }).click()
  await expect(page).toHaveURL(/\/app\/exams\//)
  return page.url().split('/').pop()!
}

async function answerWith(page: import('@playwright/test').Page, answers: Record<string, string>) {
  for (const [questionId, label] of Object.entries(answers)) {
    await page.locator(`input[type="radio"][name="${questionId}"][value="${label}"]`).check()
  }
}

async function submitAndGrade(page: import('@playwright/test').Page) {
  await page.getByRole('button', { name: '提交作答' }).click()
  await page.getByRole('button', { name: '开始判卷' }).click()
  await expect(page.getByText('判卷完成。')).toBeVisible({ timeout: 20000 })
}

test('最终模拟：按标准答案评分，答错得 0 分而非满分，刷新后结果保留', async ({ page }) => {
  const examId = await createExam(page)
  await page.goto(`/app/exams/${examId}/mock`)
  await expect(page.getByRole('heading', { name: /最终模拟 · 数据结构/ })).toBeVisible()

  // 第一套：全部选 A（内置题库里四题的正确项都不是 A）→ 应得 0 分
  await answerWith(page, WRONG_ALL_A)
  await submitAndGrade(page)
  // 分数显示形如「0 / 100 分」：断言分子而不是整串，避免把满分分母当成得分
  await expect(page.locator('.job-score')).toHaveText(/^0\s*\/\s*100\s*分$/)
  await expect(page.getByText(/错题 4 道/)).toBeVisible()
  // 逐题都要给出「你的作答」，证明评的是真实作答而不是固定结果
  await expect(page.locator('.mock-wrong-item')).toHaveCount(4)
  await expect(page.locator('.mock-wrong-answer').first()).toContainText('你的作答')
  await page.screenshot({ path: '../artifacts/mock-exam-wrong.png', fullPage: true })

  // 刷新后结果仍在（判卷结果与状态可恢复）
  await page.reload()
  await expect(page.getByText('判卷完成。')).toBeVisible({ timeout: 20000 })
  await expect(page.locator('.job-score')).toHaveText(/^0\s*\/\s*100\s*分$/)

  // 第二套：按标准答案作答 → 应得满分，且与第一套分数不同
  await page.getByRole('button', { name: '再来一套' }).click()
  await expect(page.getByRole('button', { name: '提交作答' })).toBeVisible()
  await answerWith(page, CORRECT)
  await submitAndGrade(page)
  await expect(page.locator('.job-score')).toHaveText(/^100\s*\/\s*100\s*分$/)
  await expect(page.getByText('全部答对，非常棒！')).toBeVisible()
  await page.screenshot({ path: '../artifacts/mock-exam-correct.png', fullPage: true })
})
