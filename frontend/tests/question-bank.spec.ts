import { expect, test } from '@playwright/test'

const password = 'Test-password-12345'
const xlsx = Buffer.from('UEsDBBQAAAAIAAhtM128/hnLDAAAAA8AAAATAAAAW0NvbnRlbnRfVHlwZXNdLnhtbLMJqSxILbaz0YfQAFBLAwQUAAAACAAIbTNdgtkc1RIAAAAQAAAACwAAAF9yZWxzLy5yZWxzswlKzUksyczPK87ILCjWtwMAUEsDBBQAAAAIAAhtM10NOgLubgAAAIoAAAAPAAAAeGwvd29ya2Jvb2sueG1sNY3BDoMwDEN/pcoHLLDDDqjtnTNfkI2wTpCmaiptnz+Gxsn2syX7t9b1rrq6j2zZAqTWyoBoj8RCdtHCeW8WrUJtj/WJVirTbIm5yYbXrruh0CtD9Aezv7pMwgGmn+/BHWycA/SA0eM5xfM/fgFQSwMEFAAAAAgACG0zXR6vXyoOAAAADAAAABgAAAB4bC93b3Jrc2hlZXRzL3NoZWV0MS54bWyzKc8vyi7OSE0t0bcDAFBLAQIUABQAAAAIAAhtM128/hnLDAAAAA8AAAATAAAAAAAAAAAAAACAAQAAAABbQ29udGVudF9UeXBlc10ueG1sUEsBAhQAFAAAAAgACG0zXYLZHNUSAAAAEAAAAAsAAAAAAAAAAAAAAIABPQAAAF9yZWxzLy5yZWxzUEsBAhQAFAAAAAgACG0zXQ06Au5uAAAAigAAAA8AAAAAAAAAAAAAAIABeAAAAHhsL3dvcmtib29rLnhtbFBLAQIUABQAAAAIAAhtM10er18qDgAAAAwAAAAYAAAAAAAAAAAAAACAARMBAAB4bC93b3Jrc2hlZXRzL3NoZWV0MS54bWxQSwUGAAAAAAQABAD9AAAAVwEAAAAA','base64')

async function register(page: import('@playwright/test').Page, username:string) {
  await page.goto('/register')
  await page.getByLabel('用户名', { exact:true }).fill(username)
  await page.getByLabel('密码', { exact:true }).fill(password)
  await page.getByLabel('确认密码', { exact:true }).fill(password)
  await page.getByRole('button', { name:'创建账号' }).click()
  await expect(page).toHaveURL('/app')
}

test('管理员发布公共试卷，学生上传、复制并下载私人副本', async ({ page }) => {
  const suffix = Date.now()
  const publicName = `数据结构公共试卷 ${suffix}`
  const privateName = `私人练习卷 ${suffix}`
  await register(page,'e2e_admin')
  await expect(page.getByText('e2e_admin · 管理员')).toBeVisible()
  await page.getByRole('link',{name:'题库管理'}).click()
  await page.getByRole('link',{name:'上传公共试卷'}).click()
  await page.getByLabel('新建系统科目').fill('数据结构')
  await page.getByRole('button',{name:'创建并选择'}).click()
  await page.getByLabel('试卷名称').fill(publicName)
  await page.getByLabel('学院').fill('计算机学院')
  await page.getByLabel('选择 XLSX 试卷文件').setInputFiles({name:'public.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:xlsx})
  await page.getByRole('button',{name:'保存为公共草稿'}).click()
  await expect(page).toHaveURL('/app/admin/question-bank')
  const adminPaper = page.getByRole('article').filter({hasText:publicName})
  await expect(adminPaper.getByText('草稿',{exact:true})).toBeVisible()
  await adminPaper.getByRole('button',{name:'发布',exact:true}).click()
  await expect(adminPaper.getByText('已发布',{exact:true})).toBeVisible()
  await page.getByRole('button',{name:'退出登录'}).click()

  const student = `qb_${suffix}`
  await register(page,student)
  await expect(page.getByRole('link',{name:'题库管理'})).toHaveCount(0)
  await page.getByRole('link',{name:'私人题库'}).click()
  await page.getByRole('link',{name:'上传试卷'}).click()
  await page.getByLabel('没有合适的科目？').fill('算法专题')
  await page.getByRole('button',{name:'创建并选择'}).click()
  await page.getByLabel('试卷名称').fill(privateName)
  await page.getByLabel('学院').fill('计算机学院')
  await page.getByLabel('选择 XLSX 试卷文件').setInputFiles({name:'private.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:xlsx})
  await page.getByRole('button',{name:'上传到私人题库'}).click()
  await expect(page.getByRole('heading',{name:privateName})).toBeVisible()
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button',{name:'下载 XLSX'}).click()
  expect((await downloadPromise).suggestedFilename()).toBe('private.xlsx')

  await page.getByRole('link',{name:'公共题库'}).click()
  const publicPaper = page.getByRole('article').filter({hasText:publicName})
  await expect(publicPaper).toBeVisible()
  await publicPaper.getByRole('button',{name:'加入私人题库'}).click()
  await expect(publicPaper.getByText('已加入，查看副本')).toBeVisible()
  await publicPaper.getByRole('link',{name:/已加入/}).click()
  await expect(page.getByRole('heading',{name:publicName})).toBeVisible()
  await expect(page.getByText('从公共题库复制')).toBeVisible()

  await page.setViewportSize({width:390,height:900})
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await expect(page.getByRole('complementary').getByRole('link',{name:'私人题库'})).toBeVisible()
})
