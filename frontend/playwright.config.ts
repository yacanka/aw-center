import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  // Keep browser/trace memory bounded on shared developer and CI hosts.
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'retain-on-failure'
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run build && npm run serve -- --host 127.0.0.1 --port 4173 --strictPort',
    env: { VITE_API_URL: '/' },
    url: 'http://127.0.0.1:4173/app/login',
    reuseExistingServer: false,
    timeout: 120_000
  }
})
