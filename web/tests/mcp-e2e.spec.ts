import { test, expect } from '@playwright/test'

const BASE_URL = process.env.BASE_URL ?? 'http://127.0.0.1:8100'

/** 通过 API 清理指定名称的 MCP 服务器 */
async function cleanupServer(page: import('@playwright/test').Page, name: string) {
  try {
    await page.request.delete(`${BASE_URL}/api/mcp/servers/${encodeURIComponent(name)}`)
  } catch { /* ignore */ }
}

test.describe('MCP Server Management', () => {
  test.beforeEach(async ({ page }) => {
    // 清理测试用服务器，避免残留冲突
    await cleanupServer(page, 'test-weather')
    await cleanupServer(page, 'to-remove')
    await cleanupServer(page, 'temp-weather')

    await page.goto(`${BASE_URL}/settings/mcp`)
    await page.waitForSelector('.install-section', { timeout: 10000 })
  })

  test('MCP 页面显示添加表单和使用说明', async ({ page }) => {
    await expect(page.locator('h2', { hasText: '添加 MCP 服务器' })).toBeVisible()
    await expect(page.locator('#mcp-name')).toBeVisible()
    await expect(page.locator('#mcp-url')).toBeVisible()
    await expect(page.locator('#mcp-add-btn')).toBeVisible()
    await expect(page.locator('.help-box')).toBeVisible()
  })

  test('添加按钮 - 空输入时禁用', async ({ page }) => {
    await expect(page.locator('#mcp-add-btn')).toBeDisabled()
  })

  test('添加 MCP 服务器并探测工具列表', async ({ page }) => {
    // 添加 MCP 服务器
    await page.fill('#mcp-name', 'test-weather')
    await page.fill('#mcp-url', 'http://localhost:8199/mcp')
    await page.click('#mcp-add-btn')

    // 等待成功消息
    await expect(page.locator('.msg.success')).toBeVisible({ timeout: 10000 })

    // 验证服务器卡片出现
    const card = page.locator('.skill-card[data-server-name="test-weather"]')
    await expect(card).toBeVisible()
    await expect(card.locator('.skill-name')).toHaveText('test-weather')
    await expect(card.locator('.mcp-url-display')).toContainText('http://localhost:8199/mcp')

    // 探测工具
    await card.locator('.mcp-probe-btn').click()
    await expect(page.locator('.msg.success')).toContainText('探测成功', { timeout: 15000 })

    // 验证工具 chip 显示
    await expect(card.locator('.mcp-tool-chip', { hasText: 'get_weather' })).toBeVisible()
    await expect(card.locator('.mcp-tool-chip', { hasText: 'get_forecast' })).toBeVisible()

    // 清理
    await cleanupServer(page, 'test-weather')
  })

  test('移除 MCP 服务器', async ({ page }) => {
    // 通过 API 添加
    await page.request.post(`${BASE_URL}/api/mcp/servers`, {
      data: { name: 'to-remove', url: 'http://localhost:8199/mcp' },
    })
    await page.reload()
    await page.waitForSelector('.install-section', { timeout: 10000 })

    const card = page.locator('.skill-card[data-server-name="to-remove"]')
    await expect(card).toBeVisible()

    // 移除
    page.on('dialog', d => d.accept())
    await card.locator('.btn-danger').click()
    await expect(page.locator('.msg.success')).toContainText('已移除', { timeout: 10000 })
    await expect(card).toBeHidden()
  })
})

test.describe('MCP Chat Integration', () => {
  test.beforeEach(async ({ page }) => {
    // 确保只有 "weather" 一个 MCP 服务器，清理其他
    await cleanupServer(page, 'test-weather')
    await cleanupServer(page, 'to-remove')
    await cleanupServer(page, 'temp-weather')
  })

  test('通过 MCP 工具进行天气查询对话', async ({ page }) => {
    // 确保 weather MCP 服务器已配置
    const servers = await (await page.request.get(`${BASE_URL}/api/mcp/servers`)).json()
    const hasWeather = servers.some((s: { name: string }) => s.name === 'weather')
    if (!hasWeather) {
      await page.request.post(`${BASE_URL}/api/mcp/servers`, {
        data: { name: 'weather', url: 'http://localhost:8199/mcp' },
      })
    }

    // 切到会话页面
    await page.goto(BASE_URL)
    await expect(page.locator('.chat-area')).toBeVisible({ timeout: 10000 })

    // 新会话确保干净
    const newSessionBtn = page.locator('.btn-sm', { hasText: '新会话' })
    if (await newSessionBtn.isEnabled()) {
      await newSessionBtn.click()
    }

    // 发送天气查询
    await page.fill('#input-box', '北京今天天气怎么样？')
    await page.click('#send-btn')

    // 等待 agent 使用 get_weather 工具
    await expect(page.locator('.tool-name', { hasText: 'get_weather' })).toBeVisible({ timeout: 45000 })

    // 等待工具完成
    await expect(page.locator('.tool-status.done')).toBeVisible({ timeout: 30000 })

    // 等待流式结束（输入框重新可用）
    await expect(page.locator('#input-box')).toBeEnabled({ timeout: 45000 })

    // 等待 agent 文本回复（包含天气信息）
    await expect(page.locator('.text-segment')).toBeVisible({ timeout: 5000 })

    // 验证回复包含天气关键词
    const textContent = await page.locator('.text-segment').last().textContent()
    expect(textContent).toBeTruthy()
    // mock 返回的天气数据包含"温度"和"°C"
    expect(textContent).toMatch(/温度|天气|°C|小雨|湿度/)
  })

  test('移除 MCP 服务器后 API 不返回该服务器', async ({ page }) => {
    // 通过 API 添加临时服务器
    await page.request.post(`${BASE_URL}/api/mcp/servers`, {
      data: { name: 'temp-weather', url: 'http://localhost:8199/mcp' },
    })

    // 验证已添加
    let servers = await (await page.request.get(`${BASE_URL}/api/mcp/servers`)).json()
    expect(servers.some((s: { name: string }) => s.name === 'temp-weather')).toBe(true)

    // 通过 UI 移除
    await page.goto(`${BASE_URL}/settings/mcp`)
    await page.waitForSelector('.install-section', { timeout: 10000 })

    page.on('dialog', d => d.accept())
    const card = page.locator('.skill-card[data-server-name="temp-weather"]')
    await expect(card).toBeVisible()
    await card.locator('.btn-danger').click()
    await expect(page.locator('.msg.success')).toContainText('已移除', { timeout: 10000 })

    // 验证 API 不再返回该服务器
    servers = await (await page.request.get(`${BASE_URL}/api/mcp/servers`)).json()
    const names = servers.map((s: { name: string }) => s.name)
    expect(names).not.toContain('temp-weather')
  })
})
