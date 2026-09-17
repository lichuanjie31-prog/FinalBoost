import { test, expect } from '@playwright/test'

for (const width of [390, 768, 1440]) {
  test(`首页和账号页面在 ${width}px 可操作`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 })
    await page.goto('/')
    await expect(page.getByRole('heading', { name: '把时间留给真正学懂的那一刻。' })).toBeVisible()
    await expect(page.getByText('交互示意', { exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: `../artifacts/home-${width}.png`, fullPage: true })
    await page.getByRole('link', { name: '开始我的备考' }).click()
    await expect(page).toHaveURL(/\/login/)
    await expect(page.getByLabel('用户名', { exact: true })).toBeVisible()
    await page.screenshot({ path: `../artifacts/login-${width}.png`, fullPage: true })
    await page.getByRole('link', { name: '创建账号' }).click()
    await page.getByLabel('用户名', { exact: true }).fill('student')
    await page.getByLabel('密码', { exact: true }).fill('Test-password-123')
    await page.getByLabel('确认密码', { exact: true }).fill('different-password')
    await page.getByRole('button', { name: '创建账号' }).click()
    await expect(page.getByRole('alert')).toContainText('两次输入的密码不一致')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: `../artifacts/register-${width}.png`, fullPage: true })
  })
}

test('键盘跳过导航且未登录业务路由返回登录页', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: '跳到主要内容' })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.locator('#main')).toBeFocused()
  await page.goto('/app/exams/example')
  await expect(page).toHaveURL(/\/login\?next=/)
})
