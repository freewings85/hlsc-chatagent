import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  timeout: 60000,
  retries: 0,
  use: {
    headless: true,
    baseURL: process.env.BASE_URL ?? 'http://127.0.0.1:8100',
    viewport: { width: 1280, height: 720 },
    actionTimeout: 10000,
  },
})
