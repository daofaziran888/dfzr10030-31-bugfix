import { defineConfig } from '@playwright/test'

// 受限环境下系统库装不到默认目录时，允许通过环境变量补 LD_LIBRARY_PATH。
const extraLibPath = process.env.CHROMIUM_LIB_PATH ?? ''
const env = extraLibPath
  ? { LD_LIBRARY_PATH: `${extraLibPath}:${process.env.LD_LIBRARY_PATH ?? ''}` }
  : undefined

export default defineConfig({
  testDir: './tests',
  timeout: 300_000,
  expect: { timeout: 10_000 },
  workers: 1,
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:5173',
    browserName: 'chromium',
    headless: true,
    actionTimeout: 10_000,
    launchOptions: env ? { env } : undefined,
  },
  reporter: 'line',
})
