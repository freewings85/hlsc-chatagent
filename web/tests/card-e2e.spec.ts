import { test, expect } from '@playwright/test'

const BASE_URL = process.env.BASE_URL ?? 'http://127.0.0.1:8100'

/** 通过 API 清理指定名称的 MCP 服务器 */
async function cleanupServer(page: import('@playwright/test').Page, name: string) {
  try {
    await page.request.delete(`${BASE_URL}/api/mcp/servers/${encodeURIComponent(name)}`)
  } catch { /* ignore */ }
}

/** 确保 weather MCP 服务器已配置 */
async function ensureWeatherMcp(page: import('@playwright/test').Page) {
  const servers = await (await page.request.get(`${BASE_URL}/api/mcp/servers`)).json()
  const hasWeather = servers.some((s: { name: string }) => s.name === 'weather')
  if (!hasWeather) {
    await page.request.post(`${BASE_URL}/api/mcp/servers`, {
      data: { name: 'weather', url: 'http://localhost:8199/mcp' },
    })
  }
}

// ============================================================================
// MCP 卡片测试：天气工具返回 weather 卡片
// ============================================================================

test.describe('Card - MCP Path', () => {
  test.beforeEach(async ({ page }) => {
    await cleanupServer(page, 'test-weather')
    await ensureWeatherMcp(page)
  })

  test('MCP 天气工具返回 weather 卡片并渲染', async ({ page }) => {
    await page.goto(BASE_URL)
    await expect(page.locator('.chat-area')).toBeVisible({ timeout: 10000 })

    // 新会话
    const newBtn = page.locator('.btn-sm', { hasText: '新会话' })
    if (await newBtn.isEnabled()) await newBtn.click()

    // 发送天气查询
    await page.fill('#input-box', '北京今天天气怎么样？')
    await page.click('#send-btn')

    // 等待 get_weather 工具调用 + 完成
    await expect(page.locator('.tool-name', { hasText: 'get_weather' })).toBeVisible({ timeout: 45000 })
    await expect(page.locator('.tool-status.done')).toBeVisible({ timeout: 30000 })

    // 等待流式结束
    await expect(page.locator('#input-box')).toBeEnabled({ timeout: 45000 })

    // 验证卡片渲染
    const cardBlock = page.locator('.card-block[data-card-type="weather"]')
    await expect(cardBlock).toBeVisible({ timeout: 10000 })
    await expect(cardBlock.locator('.card-type')).toHaveText('weather')

    // 验证卡片字段
    await expect(cardBlock.locator('.card-label', { hasText: 'city' })).toBeVisible()
    await expect(cardBlock.locator('.card-label', { hasText: 'temperature' })).toBeVisible()

    // 验证卡片值
    const cityValue = cardBlock.locator('.card-field', { hasText: 'city' }).locator('.card-value')
    await expect(cityValue).toContainText('北京')
  })
})

// ============================================================================
// Skill 卡片测试：card-demo skill 脚本返回 repair_shops 卡片
// ============================================================================

test.describe('Card - Skill Path', () => {
  test('Skill 脚本返回 repair_shops 卡片并渲染', async ({ page }) => {
    await page.goto(BASE_URL)
    await expect(page.locator('.chat-area')).toBeVisible({ timeout: 10000 })

    // 新会话
    const newBtn = page.locator('.btn-sm', { hasText: '新会话' })
    if (await newBtn.isEnabled()) await newBtn.click()

    // 触发 card-demo skill（关键词：修理厂）
    await page.fill('#input-box', '帮我查询附近的修理厂')
    await page.click('#send-btn')

    // 等待 Skill 工具调用
    await expect(page.locator('.tool-name', { hasText: 'Skill' })).toBeVisible({ timeout: 45000 })

    // 等待 bash 执行（skill 脚本通过 bash 执行）
    await expect(page.locator('.tool-name', { hasText: 'bash' })).toBeVisible({ timeout: 45000 })

    // 等待流式结束
    await expect(page.locator('#input-box')).toBeEnabled({ timeout: 90000 })

    // 验证卡片渲染 — 支持 tool_call_id 和 detail_type 两种引用方式
    const cardBlock = page.locator('.card-block[data-card-type="repair_shops"]')
    await expect(cardBlock).toBeVisible({ timeout: 10000 })
    await expect(cardBlock.locator('.card-type')).toHaveText('repair_shops')

    // 验证卡片包含修理厂数据
    await expect(cardBlock.locator('.card-label', { hasText: 'total' })).toBeVisible()
    await expect(cardBlock.locator('.card-label', { hasText: 'items' })).toBeVisible()
  })
})

// ============================================================================
// SSE 层验证：直接用 API 确认 tool_result_detail 事件格式
// ============================================================================

test.describe('Card - SSE Event Verification', () => {
  test.beforeEach(async ({ page }) => {
    await ensureWeatherMcp(page)
  })

  test('MCP 工具触发 tool_result_detail SSE 事件包含正确结构', async ({ page }) => {
    // 直接调 API，不依赖前端渲染
    const resp = await page.request.post(`${BASE_URL}/chat/stream`, {
      data: { session_id: 'sse-verify-mcp', message: '查询北京天气', user_id: 'test-user' },
      timeout: 60000,
    })
    const body = await resp.text()

    // 验证 tool_result_detail 事件存在
    expect(body).toContain('event: tool_result_detail')

    // 解析 tool_result_detail 事件
    const detailLine = body.split('\n').find(l => l.includes('"tool_result_detail"') && l.startsWith('data:'))
    expect(detailLine).toBeTruthy()

    const detailEvent = JSON.parse(detailLine!.replace('data: ', ''))
    const data = detailEvent.data

    // 验证结构
    expect(data.tool_call_id).toBeTruthy()
    expect(data.detail_type).toBe('weather')
    expect(data.data.success).toBe(true)
    expect(data.data.data.city).toBe('北京')
    expect(typeof data.data.data.temperature).toBe('number')
  })

  test('Skill bash 工具触发 tool_result_detail SSE 事件', async ({ page }) => {
    const resp = await page.request.post(`${BASE_URL}/chat/stream`, {
      data: { session_id: 'sse-verify-skill', message: '帮我查附近修理厂', user_id: 'test-user' },
      timeout: 60000,  // Skill 路径需要多次 LLM 调用，增加超时
    })
    const body = await resp.text()

    // 验证 tool_result_detail 事件存在
    expect(body).toContain('event: tool_result_detail')

    // 解析
    const detailLine = body.split('\n').find(l => l.includes('"tool_result_detail"') && l.startsWith('data:'))
    expect(detailLine).toBeTruthy()

    const detailEvent = JSON.parse(detailLine!.replace('data: ', ''))
    const data = detailEvent.data

    expect(data.detail_type).toBe('repair_shops')
    expect(data.data.success).toBe(true)
    expect(data.data.data.total).toBe(3)
    expect(data.data.data.items).toHaveLength(3)
    expect(data.data.data.items[0].name).toBe('远大汽修')
  })

  test('tool_result 中包含 system-reminder 提示', async ({ page }) => {
    const resp = await page.request.post(`${BASE_URL}/chat/stream`, {
      data: { session_id: 'sse-verify-reminder', message: '查北京天气', user_id: 'test-user' },
      timeout: 60000,
    })
    const body = await resp.text()

    // 找到包含 card 的 tool_result 事件
    const resultLines = body.split('\n').filter(l =>
      l.includes('"tool_result"') && l.startsWith('data:') && l.includes('card:')
    )
    expect(resultLines.length).toBeGreaterThan(0)

    // 验证 system-reminder 被追加
    const resultEvent = JSON.parse(resultLines[0].replace('data: ', ''))
    const result = typeof resultEvent.data.result === 'object'
      ? JSON.stringify(resultEvent.data.result)
      : resultEvent.data.result
    expect(result).toContain('<system-reminder>')
    expect(result).toContain('{{card:')
    expect(result).toContain('</system-reminder>')
  })
})

// ============================================================================
// 前端卡片渲染测试
// ============================================================================

test.describe('Card - Frontend Rendering', () => {
  test.beforeEach(async ({ page }) => {
    await ensureWeatherMcp(page)
  })

  test('卡片组件包含 header 和 body 结构', async ({ page }) => {
    await page.goto(BASE_URL)
    await expect(page.locator('.chat-area')).toBeVisible({ timeout: 10000 })

    const newBtn = page.locator('.btn-sm', { hasText: '新会话' })
    if (await newBtn.isEnabled()) await newBtn.click()

    await page.fill('#input-box', '北京天气')
    await page.click('#send-btn')

    // 等待流式结束
    await expect(page.locator('#input-box')).toBeEnabled({ timeout: 60000 })

    // 验证卡片 DOM 结构
    await expect(page.locator('.card-block')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('.card-header .card-icon')).toBeVisible()
    await expect(page.locator('.card-header .card-type')).toBeVisible()
    await expect(page.locator('.card-body .card-field')).toHaveCount(5) // city, condition, temperature, humidity, unit
  })
})
