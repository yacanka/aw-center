import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './viewer-e2e',
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:28754' }
})
