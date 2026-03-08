import { test, expect } from '@playwright/test'

const BASE_URL = process.env.VITE_URL ?? 'http://127.0.0.1:5174'

// OpenClaw github skill (public, stable)
const GITHUB_SKILL_URL =
  'https://github.com/openclaw/openclaw/tree/main/skills/github'

test.describe('Skill Manager', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE_URL)
    // 等待页面加载完成（skill 列表请求完成）
    await page.waitForSelector('.skill-card, .empty', { timeout: 10000 })
  })

  test('页面加载 - 显示标题和安装区域', async ({ page }) => {
    await expect(page.locator('h1')).toHaveText('Skill Manager')
    await expect(page.locator('.install-input')).toBeVisible()
    await expect(page.locator('.btn-primary')).toBeVisible()
  })

  test('初始状态 - 显示 bundled example skill', async ({ page }) => {
    const exampleCard = page.locator('.skill-card', { hasText: 'example' })
    await expect(exampleCard).toBeVisible()
    await expect(exampleCard.locator('.badge-bundled')).toHaveText('bundled')
    // bundled skill 不应有卸载按钮
    await expect(exampleCard.locator('.btn-danger')).toBeHidden()
  })

  test('安装按钮 - 空输入时禁用', async ({ page }) => {
    const btn = page.locator('.btn-primary')
    await expect(btn).toBeDisabled()
  })

  test('安装按钮 - 有输入时启用', async ({ page }) => {
    await page.fill('.install-input', 'https://example.com/SKILL.md')
    const btn = page.locator('.btn-primary')
    await expect(btn).toBeEnabled()
  })

  test('安装无效 URL - 显示错误消息', async ({ page }) => {
    await page.fill('.install-input', 'not-a-url')
    await page.click('.btn-primary')
    await expect(page.locator('.message.error')).toBeVisible({ timeout: 10000 })
  })

  test('从 GitHub 安装真实 skill', async ({ page }) => {
    // 安装 OpenClaw 的 github skill
    await page.fill('.install-input', GITHUB_SKILL_URL)
    await page.click('.btn-primary')

    // 等待安装成功消息
    await expect(page.locator('.message.success')).toBeVisible({ timeout: 30000 })
    await expect(page.locator('.message.success')).toContainText('已安装')

    // 验证 skill 出现在列表中
    const githubCard = page.locator('.skill-card', { hasText: 'github' })
    await expect(githubCard).toBeVisible()
    await expect(githubCard.locator('.badge-project')).toHaveText('project')

    // project skill 应有卸载按钮
    await expect(githubCard.locator('.btn-danger')).toBeVisible()

    // 输入框应已清空
    await expect(page.locator('.install-input')).toHaveValue('')
  })

  test('卸载已安装的 skill', async ({ page }) => {
    // 先安装
    await page.fill('.install-input', GITHUB_SKILL_URL)
    await page.click('.btn-primary')
    await expect(page.locator('.message.success')).toBeVisible({ timeout: 30000 })

    // 确认 github skill 存在
    const githubCard = page.locator('.skill-card', { hasText: 'github' })
    await expect(githubCard).toBeVisible()

    // 点击卸载
    page.on('dialog', dialog => dialog.accept())
    await githubCard.locator('.btn-danger').click()

    // 等待卸载成功消息
    await expect(page.locator('.message.success')).toContainText('已卸载', { timeout: 10000 })

    // github skill 应从列表消失
    await expect(githubCard).toBeHidden()
  })

  test('帮助区域 - 显示支持的 URL 格式', async ({ page }) => {
    const help = page.locator('.help-section')
    await expect(help).toBeVisible()
    await expect(help).toContainText('GitHub 目录')
    await expect(help).toContainText('Raw 直链')
  })

  test('安装后 skill 数量增加', async ({ page }) => {
    // 记录初始数量
    const countText = await page.locator('.skill-count').textContent()
    const initialCount = parseInt(countText?.match(/\d+/)?.[0] ?? '0')

    // 安装
    await page.fill('.install-input', GITHUB_SKILL_URL)
    await page.click('.btn-primary')
    await expect(page.locator('.message.success')).toBeVisible({ timeout: 30000 })

    // 验证数量增加
    const newCountText = await page.locator('.skill-count').textContent()
    const newCount = parseInt(newCountText?.match(/\d+/)?.[0] ?? '0')
    expect(newCount).toBe(initialCount + 1)

    // 清理：卸载
    page.on('dialog', dialog => dialog.accept())
    const githubCard = page.locator('.skill-card', { hasText: 'github' })
    await githubCard.locator('.btn-danger').click()
    await expect(page.locator('.message.success')).toContainText('已卸载', { timeout: 10000 })
  })
})
