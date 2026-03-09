import { test, expect } from '@playwright/test'

const BASE_URL = process.env.BASE_URL ?? 'http://127.0.0.1:8100'

// OpenClaw github skill (public, stable)
const GITHUB_SKILL_URL =
  'https://github.com/openclaw/openclaw/tree/main/skills/github'

test.describe('Skill Manager', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to skill management page via settings
    await page.goto(`${BASE_URL}/settings/skills`)
    await page.waitForSelector('.skill-card, .empty', { timeout: 10000 })
  })

  test('页面加载 - 显示设置页面布局', async ({ page }) => {
    // 顶栏有 ChatAgent logo 和 设置导航
    await expect(page.locator('.logo-text')).toHaveText('ChatAgent')
    // 侧栏有 Skills 和 MCP 导航
    await expect(page.locator('.nav-item', { hasText: 'Skills' })).toBeVisible()
    await expect(page.locator('.nav-item', { hasText: 'MCP' })).toBeVisible()
    // 安装区域
    await expect(page.locator('.install-input')).toBeVisible()
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

  test('安装无效 URL - 显示错误消息', async ({ page }) => {
    await page.fill('.install-input', 'not-a-url')
    await page.click('.btn-primary')
    await expect(page.locator('.msg.error')).toBeVisible({ timeout: 10000 })
  })

  test('从 GitHub 安装真实 skill', async ({ page }) => {
    await page.fill('.install-input', GITHUB_SKILL_URL)
    await page.click('.btn-primary')

    await expect(page.locator('.msg.success')).toBeVisible({ timeout: 30000 })
    await expect(page.locator('.msg.success')).toContainText('已安装')

    const githubCard = page.locator('.skill-card', { hasText: 'github' })
    await expect(githubCard).toBeVisible()
    await expect(githubCard.locator('.badge-project')).toHaveText('project')
    await expect(githubCard.locator('.btn-danger')).toBeVisible()
    await expect(page.locator('.install-input')).toHaveValue('')
  })

  test('卸载已安装的 skill', async ({ page }) => {
    // 先安装
    await page.fill('.install-input', GITHUB_SKILL_URL)
    await page.click('.btn-primary')
    await expect(page.locator('.msg.success')).toBeVisible({ timeout: 30000 })

    const githubCard = page.locator('.skill-card', { hasText: 'github' })
    await expect(githubCard).toBeVisible()

    page.on('dialog', dialog => dialog.accept())
    await githubCard.locator('.btn-danger').click()

    await expect(page.locator('.msg.success')).toContainText('已卸载', { timeout: 10000 })
    await expect(githubCard).toBeHidden()
  })

  test('导航到会话页面再回来', async ({ page }) => {
    // 点击 "会话" 导航
    await page.locator('.app-nav-item', { hasText: '会话' }).click()
    await expect(page.locator('.chat-area')).toBeVisible({ timeout: 10000 })

    // 点击 "设置" 导航回来
    await page.locator('.app-nav-item', { hasText: '设置' }).click()
    await expect(page.locator('.install-input')).toBeVisible({ timeout: 10000 })
  })

  test('MCP 页面 - 显示添加表单', async ({ page }) => {
    await expect(page.locator('.nav-item', { hasText: 'MCP' })).toBeVisible({ timeout: 5000 })
    await page.locator('.nav-item', { hasText: 'MCP' }).click()
    await expect(page.locator('h2', { hasText: '添加 MCP 服务器' })).toBeVisible({ timeout: 10000 })
    await expect(page.locator('#mcp-name')).toBeVisible()
    await expect(page.locator('#mcp-url')).toBeVisible()
  })
})

test.describe('Chat Page', () => {
  test('首页显示会话页面', async ({ page }) => {
    await page.goto(BASE_URL)
    await expect(page.locator('.chat-area')).toBeVisible()
    await expect(page.locator('.empty-hint')).toBeVisible()
    await expect(page.locator('.chat-input')).toBeVisible()
  })
})
